import uuid

import pytest

from app.models.room import Room
from app.models.room_task_script import RoomTaskScript
from app.models.task import Task
from app.models.user import User, UserRole
from app.services import room_task_script_service
from app.services import task_script_service


@pytest.mark.asyncio
async def test_task_script_state_is_isolated_between_rooms_sharing_same_task(fake_db, monkeypatch):
    shared_task_id = uuid.uuid4()
    task = Task(
        id=shared_task_id,
        title="Shared Task",
        created_by=uuid.uuid4(),
        scripts={
            "current_status": "Initial status",
            "next_goal": "Initial goal",
            "history": [],
            "pending_proposal": None,
        },
    )

    room_a = Room(id=uuid.uuid4(), name="Room A", created_by=uuid.uuid4())
    room_a.task_id = shared_task_id
    room_b = Room(id=uuid.uuid4(), name="Room B", created_by=uuid.uuid4())
    room_b.task_id = shared_task_id
    room_c = Room(id=uuid.uuid4(), name="Room C", created_by=uuid.uuid4())
    room_c.task_id = shared_task_id

    student_a = User(
        id=uuid.uuid4(),
        username="student_a",
        password_hash="x",
        display_name="Student A",
        role=UserRole.student,
    )
    student_b = User(
        id=uuid.uuid4(),
        username="student_b",
        password_hash="x",
        display_name="Student B",
        role=UserRole.student,
    )

    async def _fake_get_task(_db, _task_id):
        return task

    async def _fake_generate_facilitator_proposal(_room_id):
        return {
            "current_status": "A组完成初步数据分析",
            "next_goal": "继续解释热岛效应成因",
            "change_reason": "测试任务流程跨房间隔离",
        }

    async def _fake_broadcast(*_args, **_kwargs):
        return None

    async def _fake_touch_activity(*_args, **_kwargs):
        return None

    lock_state = {"room_a": None}

    async def _fake_get_lock_raw(room_id: str):
        if room_id == str(room_a.id):
            return lock_state["room_a"]
        return None

    async def _fake_release_lock(_room_id, _current_user, _lease_id):
        lock_state["room_a"] = None
        return {"released": True}

    room_a_script = RoomTaskScript(
        id=uuid.uuid4(),
        room_id=room_a.id,
        task_id=shared_task_id,
        scripts={"current_status": "Initial status", "next_goal": "Initial goal", "history": [], "pending_proposal": None},
    )
    room_b_script = RoomTaskScript(
        id=uuid.uuid4(),
        room_id=room_b.id,
        task_id=shared_task_id,
        scripts={"current_status": "Initial status", "next_goal": "Initial goal", "history": [], "pending_proposal": None},
    )
    room_c_script = RoomTaskScript(
        id=uuid.uuid4(),
        room_id=room_c.id,
        task_id=shared_task_id,
        scripts={"current_status": "Initial status", "next_goal": "Initial goal", "history": [], "pending_proposal": None},
    )

    script_map = {
        room_a.id: room_a_script,
        room_b.id: room_b_script,
        room_c.id: room_c_script,
    }

    async def _fake_get_or_create(_db, _room):
        return script_map[_room.id]

    monkeypatch.setattr(task_script_service.task_service, "get_task", _fake_get_task)
    monkeypatch.setattr(room_task_script_service.task_service, "get_task", _fake_get_task)
    monkeypatch.setattr(task_script_service, "_generate_facilitator_proposal", _fake_generate_facilitator_proposal)
    monkeypatch.setattr(task_script_service, "_broadcast_task_script_updated", _fake_broadcast)
    monkeypatch.setattr(task_script_service, "_touch_room_activity", _fake_touch_activity)
    monkeypatch.setattr(task_script_service, "_get_lock_raw", _fake_get_lock_raw)
    monkeypatch.setattr(task_script_service, "release_task_script_lock", _fake_release_lock)
    monkeypatch.setattr(task_script_service, "get_or_create_room_task_script", _fake_get_or_create)

    result_a = await task_script_service.propose_facilitator_update(fake_db, room_a, student_a)
    proposal_a = result_a["pending_proposal"]
    assert proposal_a is not None

    state_b = await task_script_service.get_task_script_state(fake_db, room_b)
    state_c = await task_script_service.get_task_script_state(fake_db, room_c)
    assert state_b["pending_proposal"] is None
    assert state_c["pending_proposal"] is None

    result_b = await task_script_service.propose_facilitator_update(fake_db, room_b, student_b)
    proposal_b = result_b["pending_proposal"]
    assert proposal_b is not None
    assert proposal_a["id"] != proposal_b["id"]

    lock_state["room_a"] = {
        "user_id": str(student_a.id),
        "proposal_id": str(proposal_a["id"]),
        "lease_id": "lease-a",
    }
    confirm_a = await task_script_service.confirm_pending_proposal(
        fake_db,
        room_a,
        student_a,
        proposal_id=str(proposal_a["id"]),
        lease_id="lease-a",
    )

    assert confirm_a["pending_proposal"] is None
    assert confirm_a["current_status"] == proposal_a["current_status"]
    assert len(confirm_a["history"]) == 1

    after_b = await task_script_service.get_task_script_state(fake_db, room_b)
    after_c = await task_script_service.get_task_script_state(fake_db, room_c)
    assert after_b["pending_proposal"] is not None
    assert after_b["pending_proposal"]["id"] == proposal_b["id"]
    assert after_b["history"] == []
    assert after_c["pending_proposal"] is None
    assert after_c["history"] == []
