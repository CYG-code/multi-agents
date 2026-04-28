from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.agents import context_builder


class _FakeAsyncSessionCtx:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeSession:
    def __init__(self, room=None, task=None, members=None):
        self._room = room
        self._task = task
        self._members = members or []

    async def get(self, model, _id):
        name = getattr(model, "__name__", "")
        if name == "Room":
            return self._room
        if name == "Task":
            return self._task
        return None

    async def execute(self, _stmt):
        class _Result:
            def __init__(self, members):
                self._members = members

            def fetchall(self):
                return [SimpleNamespace(id=item["id"], display_name=item["display_name"]) for item in self._members]

        return _Result(self._members)


@pytest.mark.asyncio
async def test_get_room_context_fallback(monkeypatch):
    monkeypatch.setattr(
        context_builder,
        "AsyncSessionLocal",
        lambda: _FakeAsyncSessionCtx(_FakeSession()),
    )
    async def _fake_recent_interventions(*_args, **_kwargs):
        return []

    monkeypatch.setattr(context_builder, "get_recent_interventions", _fake_recent_interventions)

    result = await context_builder.get_room_context("room-1")

    assert result["task_description"] == "讨论一个社会议题并形成可执行结论"
    assert result["members_info"] == "暂无成员信息"
    assert result["elapsed_minutes"] == 0
    assert result["current_phase"].startswith("前期")


@pytest.mark.asyncio
async def test_get_room_context_derives_phase_and_members(monkeypatch):
    room = SimpleNamespace(
        id="room-2",
        task_id="task-2",
        timer_started_at=datetime.now(timezone.utc) - timedelta(minutes=76),
        timer_stopped_at=None,
    )
    task = SimpleNamespace(requirements="Req", scripts={"current_status": "S", "next_goal": "G"})
    members = [
        {"id": "u1", "display_name": "Alice"},
        {"id": "u2", "display_name": "Bob"},
    ]

    monkeypatch.setattr(
        context_builder,
        "AsyncSessionLocal",
        lambda: _FakeAsyncSessionCtx(_FakeSession(room=room, task=task, members=members)),
    )
    async def _fake_recent_interventions(*_args, **_kwargs):
        return []

    monkeypatch.setattr(context_builder, "get_recent_interventions", _fake_recent_interventions)

    result = await context_builder.get_room_context("room-2")

    assert result["task_description"] == "Req"
    assert result["members_info"] == "Alice、Bob"
    assert result["elapsed_minutes"] >= 75
    assert result["current_phase"].startswith("后期")
    assert result["phase_goal"]
