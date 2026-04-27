import uuid

import pytest

from app.models.user import User, UserRole
from app.services import writing_submit_service


class _FakeRedis:
    def __init__(self):
        self._store = {}

    async def get(self, key):
        return self._store.get(key)

    async def set(self, key, value):
        self._store[key] = value

    async def delete(self, key):
        self._store.pop(key, None)


def _build_user(name: str) -> User:
    return User(
        id=uuid.uuid4(),
        username=name,
        password_hash="x",
        display_name=name,
        role=UserRole.student,
    )


@pytest.mark.asyncio
async def test_confirm_writing_submit_requires_three_students(monkeypatch):
    fake_redis = _FakeRedis()
    monkeypatch.setattr(writing_submit_service, "get_redis_client", lambda: fake_redis)
    room_id = "room-1"

    s1 = _build_user("s1")
    s2 = _build_user("s2")
    s3 = _build_user("s3")

    state1, finalized1 = await writing_submit_service.confirm_writing_submit(room_id, s1)
    state2, finalized2 = await writing_submit_service.confirm_writing_submit(room_id, s2)
    state3, finalized3 = await writing_submit_service.confirm_writing_submit(room_id, s3)

    assert finalized1 is False
    assert finalized2 is False
    assert finalized3 is True
    assert len(state1["confirmations"]) == 1
    assert len(state2["confirmations"]) == 2
    assert len(state3["confirmations"]) == 3
    assert state3["final_submitted_at"] is not None


@pytest.mark.asyncio
async def test_clear_writing_submit_state_resets(monkeypatch):
    fake_redis = _FakeRedis()
    monkeypatch.setattr(writing_submit_service, "get_redis_client", lambda: fake_redis)
    room_id = "room-2"
    student = _build_user("s1")

    await writing_submit_service.confirm_writing_submit(room_id, student)
    state = await writing_submit_service.clear_writing_submit_state(room_id)

    assert state["confirmations"] == []
    assert state["final_submitted_at"] is None
