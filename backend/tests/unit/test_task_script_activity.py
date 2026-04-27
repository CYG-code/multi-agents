import uuid

import pytest

from app.models.room import Room
from app.models.task import Task
from app.models.user import User, UserRole
from app.services import task_script_service


class _FakeRedis:
    def __init__(self):
        self.data = {}

    async def get(self, key):
        return self.data.get(key)

    async def set(self, key, value, nx=False, ex=None):
        if nx and key in self.data:
            return False
        self.data[key] = value
        return True

    async def setex(self, key, _ttl, value):
        self.data[key] = value
        return True


@pytest.mark.asyncio
async def test_acquire_task_script_lock_touches_room_activity(fake_db, monkeypatch):
    room = Room(id=uuid.uuid4(), name="R1", created_by=uuid.uuid4())
    room.task_id = uuid.uuid4()
    task = Task(
        id=room.task_id,
        title="T1",
        created_by=uuid.uuid4(),
        scripts={
            "current_status": "S",
            "next_goal": "G",
            "history": [],
            "pending_proposal": {
                "id": "p-1",
                "agent_role": "facilitator",
                "current_status": "S2",
                "next_goal": "G2",
            },
        },
    )
    student = User(
        id=uuid.uuid4(),
        username="s1",
        password_hash="x",
        display_name="Student 1",
        role=UserRole.student,
    )
    fake_redis = _FakeRedis()
    touched = []

    async def _fake_get_task(_db, _task_id):
        return task

    async def _fake_touch(room_id):
        touched.append(room_id)

    async def _noop_broadcast(*_args, **_kwargs):
        return None

    monkeypatch.setattr(task_script_service.task_service, "get_task", _fake_get_task)
    monkeypatch.setattr(task_script_service, "get_redis_client", lambda: fake_redis)
    monkeypatch.setattr(task_script_service, "_touch_room_activity", _fake_touch)
    monkeypatch.setattr(task_script_service, "_broadcast_task_script_updated", _noop_broadcast)

    result = await task_script_service.acquire_task_script_lock(fake_db, room, student)

    assert result["acquired"] is True
    assert touched == [str(room.id)]
