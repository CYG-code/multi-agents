import uuid

import pytest
from fastapi import HTTPException

from app.models.room import Room
from app.models.task import Task
from app.models.user import User, UserRole
from app.services import task_script_service


@pytest.mark.asyncio
async def test_propose_facilitator_update_sets_pending_proposal(fake_db, monkeypatch):
    room = Room(id=uuid.uuid4(), name="R1", created_by=uuid.uuid4())
    room.task_id = uuid.uuid4()
    task = Task(id=room.task_id, title="T1", created_by=uuid.uuid4(), scripts="旧状态")
    user = User(
        id=uuid.uuid4(),
        username="s1",
        password_hash="x",
        display_name="Student 1",
        role=UserRole.student,
    )

    async def _fake_get_task(_db, _task_id):
        return task

    async def _fake_generate(_room_id):
        return {
            "current_status": "已完成问题拆解",
            "next_goal": "收敛两个可行方案",
            "change_reason": "讨论已进入方案比较阶段",
        }

    monkeypatch.setattr(task_script_service.task_service, "get_task", _fake_get_task)
    monkeypatch.setattr(task_script_service, "_generate_facilitator_proposal", _fake_generate)

    result = await task_script_service.propose_facilitator_update(fake_db, room, user)

    assert result["current_status"] == "旧状态"
    assert result["next_goal"] == ""
    assert result["pending_proposal"]["agent_role"] == "facilitator"
    assert result["pending_proposal"]["next_goal"] == "收敛两个可行方案"
    assert fake_db.commits == 1
    assert fake_db.refreshes == 1


@pytest.mark.asyncio
async def test_confirm_pending_proposal_applies_and_records_history_with_student_adjustments(fake_db, monkeypatch):
    room = Room(id=uuid.uuid4(), name="R1", created_by=uuid.uuid4())
    room.task_id = uuid.uuid4()
    task = Task(
        id=room.task_id,
        title="T1",
        created_by=uuid.uuid4(),
        scripts={
            "current_status": "状态A",
            "next_goal": "目标A",
            "history": [],
            "pending_proposal": {
                "id": "p-1",
                "agent_role": "facilitator",
                "current_status": "状态B",
                "next_goal": "目标B",
                "change_reason": "需要推进",
            },
        },
    )
    user = User(
        id=uuid.uuid4(),
        username="s1",
        password_hash="x",
        display_name="Student 1",
        role=UserRole.student,
    )

    async def _fake_get_task(_db, _task_id):
        return task

    monkeypatch.setattr(task_script_service.task_service, "get_task", _fake_get_task)

    result = await task_script_service.confirm_pending_proposal(
        fake_db,
        room,
        user,
        overrides={
            "current_status": "状态B-学生改",
            "next_goal": "目标B-学生改",
            "student_feedback": "建议先验证关键假设再推进。",
        },
    )

    assert result["pending_proposal"] is None
    assert result["current_status"] == "状态B-学生改"
    assert result["next_goal"] == "目标B-学生改"
    assert len(result["history"]) == 1
    assert result["history"][0]["id"] == "p-1"
    assert result["history"][0]["confirmed_by"] == str(user.id)
    assert result["history"][0]["student_adjusted"] is True
    assert result["history"][0]["student_feedback"] == "建议先验证关键假设再推进。"
    assert result["history"][0]["facilitator_suggested_current_status"] == "状态B"
    assert fake_db.commits == 1
    assert fake_db.refreshes == 1


@pytest.mark.asyncio
async def test_confirm_pending_proposal_raises_when_missing_pending(fake_db, monkeypatch):
    room = Room(id=uuid.uuid4(), name="R1", created_by=uuid.uuid4())
    room.task_id = uuid.uuid4()
    task = Task(
        id=room.task_id,
        title="T1",
        created_by=uuid.uuid4(),
        scripts={"current_status": "状态A", "next_goal": "目标A", "history": [], "pending_proposal": None},
    )
    user = User(
        id=uuid.uuid4(),
        username="s1",
        password_hash="x",
        display_name="Student 1",
        role=UserRole.student,
    )

    async def _fake_get_task(_db, _task_id):
        return task

    monkeypatch.setattr(task_script_service.task_service, "get_task", _fake_get_task)

    with pytest.raises(HTTPException) as exc:
        await task_script_service.confirm_pending_proposal(fake_db, room, user)

    assert exc.value.status_code == 400
    assert "待确认提案" in exc.value.detail
