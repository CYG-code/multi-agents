import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.models.room import Room
from app.models.user import User, UserRole
from app.websocket import handlers
from tests.conftest import FakeExecuteResult


def _build_room(agent_mode: str) -> Room:
    room = Room(
        id=uuid.uuid4(),
        name=f"smoke-{agent_mode}",
        created_by=uuid.uuid4(),
    )
    room.agent_mode = agent_mode
    room.status = "waiting"
    room.created_at = datetime.now(timezone.utc)
    return room


def _mention_cfg(entry_queue_enabled: bool = False):
    return SimpleNamespace(
        mention=SimpleNamespace(enabled=True, priority=0, max_mentions_per_message=5),
        timing=SimpleNamespace(mention_entry_enabled=entry_queue_enabled, mention_entry_queue_max_wait_sec=60),
    )


@pytest.mark.parametrize("agent_mode", ["none", "single", "multi"])
def test_create_room_and_get_room_preserve_agent_mode(client, monkeypatch, agent_mode):
    room = _build_room(agent_mode)

    async def _fake_create_room(_db, data, _user_id):
        room.name = data.name
        room.agent_mode = data.agent_mode
        return room

    async def _fake_get_room(_db, _room_id):
        return room

    async def _fake_member_count(_db, _room_id):
        return 3

    async def _fake_student_count(_db, _room_id):
        return 3

    monkeypatch.setattr("app.routers.rooms.room_service.create_room", _fake_create_room)
    monkeypatch.setattr("app.routers.rooms.room_service.get_room", _fake_get_room)
    monkeypatch.setattr("app.routers.rooms.room_service.get_member_count", _fake_member_count)
    monkeypatch.setattr("app.routers.rooms.room_service.get_student_count", _fake_student_count)
    async def _fake_online_count(_room_id):
        return 3

    monkeypatch.setattr("app.routers.rooms._get_online_count", _fake_online_count)

    create_resp = client.post("/api/rooms", json={"name": f"Room-{agent_mode}", "agent_mode": agent_mode})
    assert create_resp.status_code == 201
    assert create_resp.json()["agent_mode"] == agent_mode

    detail_resp = client.get(f"/api/rooms/{room.id}")
    assert detail_resp.status_code == 200
    assert detail_resp.json()["agent_mode"] == agent_mode
    assert detail_resp.json()["member_count"] == 3


def test_student_can_join_room_in_any_mode(client, monkeypatch):
    room = _build_room("none")
    joined = {"called": False}

    async def _fake_get_room(_db, _room_id):
        return room

    async def _fake_join_room(_db, _room_id, _user_id):
        joined["called"] = True

    monkeypatch.setattr("app.routers.rooms.room_service.get_room", _fake_get_room)
    monkeypatch.setattr("app.routers.rooms.room_service.join_room", _fake_join_room)

    resp = client.post(f"/api/rooms/{room.id}/join")
    assert resp.status_code == 200
    assert joined["called"] is True


def test_writing_doc_state_available_in_none_single_multi(client, fake_db, monkeypatch):
    fake_db.execute_result = FakeExecuteResult(scalar_value=object())

    async def _fake_get_room(_db, _room_id):
        mode = getattr(_fake_get_room, "mode", "multi")
        room = _build_room(mode)
        room.id = _room_id
        return room

    async def _fake_get_doc_state(_room_id):
        return {"content": "Draft content", "version": 2, "updated_at": None, "updated_by": None}

    monkeypatch.setattr("app.routers.rooms.room_service.get_room", _fake_get_room)
    monkeypatch.setattr("app.routers.rooms.writing_doc_service.get_writing_doc_state", _fake_get_doc_state)

    room_id = str(uuid.uuid4())
    for mode in ("none", "single", "multi"):
        _fake_get_room.mode = mode
        resp = client.get(f"/api/rooms/{room_id}/writing-doc")
        assert resp.status_code == 200
        assert resp.json()["content"] == "Draft content"
        assert resp.json()["version"] == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("agent_mode", ["none", "single", "multi"])
async def test_plain_chat_message_works_in_all_modes(monkeypatch, agent_mode):
    calls = {"saved": 0, "broadcast": 0}

    async def _fake_save(_db, _room_id, _user_id, content, _mentions, **_kwargs):
        calls["saved"] += 1

        class _Msg:
            def __init__(self, text: str):
                self.id = uuid.uuid4()
                self.seq_num = 1
                self.content = text
                self.created_at = None

        return _Msg(content)

    async def _fake_broadcast(_room_id, payload):
        if payload.get("type") == "chat:new_message":
            calls["broadcast"] += 1

    monkeypatch.setattr(handlers.MessageService, "save_student_message", _fake_save)
    monkeypatch.setattr(handlers.manager, "broadcast_to_room", _fake_broadcast)
    async def _fake_room_mode(_room_id):
        return agent_mode

    monkeypatch.setattr(handlers, "get_room_agent_mode", _fake_room_mode)

    user = User(
        id=uuid.uuid4(),
        username="student-smoke",
        password_hash="x",
        display_name="Student Smoke",
        role=UserRole.student,
    )

    await handlers.handle_chat_message(
        data={"type": "chat:message", "content": f"hello-{agent_mode}", "mentions": []},
        room_id="room-smoke",
        user=user,
        db=object(),
    )

    assert calls["saved"] == 1
    assert calls["broadcast"] == 1


@pytest.mark.asyncio
async def test_none_mode_mention_creates_no_agent_task_and_no_agent_messages(monkeypatch):
    user = User(
        id=uuid.uuid4(),
        username="student-none",
        password_hash="x",
        display_name="Student None",
        role=UserRole.student,
    )
    enqueued = []
    created_entries = []
    broadcasts = []

    async def _fake_enqueue(_room_id, task, delay_seconds=0):
        enqueued.append((task, delay_seconds))
        return {"task_id": "task-1", **task}

    async def _fake_create_entry(**kwargs):
        created_entries.append(kwargs)
        return {"entry_id": "entry-1", **kwargs}

    async def _fake_broadcast(_room_id, payload):
        broadcasts.append(payload)

    async def _fake_room_mode(_room_id):
        return "none"

    monkeypatch.setattr(handlers, "get_room_agent_mode", _fake_room_mode)
    monkeypatch.setattr(handlers, "get_agent_settings", lambda: _mention_cfg(entry_queue_enabled=False))
    monkeypatch.setattr(handlers, "enqueue_task", _fake_enqueue)
    monkeypatch.setattr(handlers, "create_mention_entry", _fake_create_entry)
    monkeypatch.setattr(handlers.manager, "broadcast_to_room", _fake_broadcast)

    await handlers._trigger_mentions(
        room_id="room-none",
        source_message_id="msg-1",
        user=user,
        mentions=["facilitator", "socratic"],
    )

    assert enqueued == []
    assert created_entries == []
    assert broadcasts == []


@pytest.mark.asyncio
async def test_single_mode_allows_only_socratic(monkeypatch):
    user = User(
        id=uuid.uuid4(),
        username="student-single",
        password_hash="x",
        display_name="Student Single",
        role=UserRole.student,
    )
    enqueued_roles = []
    broadcasts = []

    async def _fake_enqueue(_room_id, task, delay_seconds=0):
        enqueued_roles.append(task["agent_role"])
        return {"task_id": f"task-{task['agent_role']}", **task}

    async def _fake_broadcast(_room_id, payload):
        broadcasts.append(payload)

    async def _fake_room_mode(_room_id):
        return "single"

    monkeypatch.setattr(handlers, "get_room_agent_mode", _fake_room_mode)
    monkeypatch.setattr(handlers, "get_agent_settings", lambda: _mention_cfg(entry_queue_enabled=False))
    monkeypatch.setattr(handlers, "enqueue_task", _fake_enqueue)
    monkeypatch.setattr(handlers.manager, "broadcast_to_room", _fake_broadcast)

    await handlers._trigger_mentions(
        room_id="room-single",
        source_message_id="msg-2",
        user=user,
        mentions=["facilitator", "socratic", "summarizer"],
    )

    assert enqueued_roles == ["socratic"]
    ack_roles = [p.get("agent_role") for p in broadcasts if p.get("type") == "agent:ack"]
    queued_roles = [p.get("agent_role") for p in broadcasts if p.get("type") == "agent:queued"]
    assert ack_roles == ["socratic"]
    assert queued_roles == ["socratic"]


@pytest.mark.asyncio
async def test_multi_mode_keeps_existing_multi_agent_mentions(monkeypatch):
    user = User(
        id=uuid.uuid4(),
        username="student-multi",
        password_hash="x",
        display_name="Student Multi",
        role=UserRole.student,
    )
    enqueued_roles = []

    async def _fake_enqueue(_room_id, task, delay_seconds=0):
        enqueued_roles.append(task["agent_role"])
        return {"task_id": f"task-{task['agent_role']}", **task}

    async def _fake_broadcast(_room_id, _payload):
        return None

    async def _fake_room_mode(_room_id):
        return "multi"

    monkeypatch.setattr(handlers, "get_room_agent_mode", _fake_room_mode)
    monkeypatch.setattr(handlers, "get_agent_settings", lambda: _mention_cfg(entry_queue_enabled=False))
    monkeypatch.setattr(handlers, "enqueue_task", _fake_enqueue)
    monkeypatch.setattr(handlers.manager, "broadcast_to_room", _fake_broadcast)

    await handlers._trigger_mentions(
        room_id="room-multi",
        source_message_id="msg-3",
        user=user,
        mentions=["facilitator", "summarizer"],
    )

    assert enqueued_roles == ["facilitator", "summarizer"]
