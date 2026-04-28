import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.models.user import User, UserRole
from app.websocket import handlers


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeDB:
    def __init__(self, value=None):
        self.value = value
        self.calls = 0

    async def execute(self, _stmt):
        self.calls += 1
        return _ScalarResult(self.value)


@pytest.mark.asyncio
async def test_verify_token_returns_none_for_invalid_payload(monkeypatch):
    db = _FakeDB()
    monkeypatch.setattr(handlers, "decode_access_token", lambda _token: {})

    result = await handlers.verify_token("token", db)

    assert result is None
    assert db.calls == 0


@pytest.mark.asyncio
async def test_verify_token_returns_user_for_valid_payload(monkeypatch):
    user_id = uuid.uuid4()
    expected_user = User(
        id=user_id,
        username="student_1",
        password_hash="x",
        display_name="Student 1",
        role=UserRole.student,
    )
    db = _FakeDB(expected_user)
    monkeypatch.setattr(handlers, "decode_access_token", lambda _token: {"sub": str(user_id), "jti": "jti-1"})

    async def _fake_get_active_jti(_user_id):
        return "jti-1"

    monkeypatch.setattr(handlers, "get_user_active_session_jti", _fake_get_active_jti)

    result = await handlers.verify_token("token", db)

    assert result == (expected_user, "jti-1")
    assert db.calls == 1


@pytest.mark.asyncio
async def test_is_room_member_returns_false_for_invalid_room_id():
    db = _FakeDB(value=object())

    result = await handlers.is_room_member(uuid.uuid4(), "not-a-uuid", db)

    assert result is False
    assert db.calls == 0


@pytest.mark.asyncio
async def test_trigger_mentions_emits_supported_and_unsupported_events(monkeypatch):
    calls = []
    enqueued = []
    user = User(
        id=uuid.uuid4(),
        username="student_1",
        password_hash="x",
        display_name="Student 1",
        role=UserRole.student,
    )

    async def _fake_broadcast(room_id, payload):
        calls.append((room_id, payload))

    async def _fake_enqueue(room_id, task, delay_seconds=0):
        enqueued.append((room_id, task, delay_seconds))
        return {"task_id": "task-1", **task}

    class _Mention:
        enabled = True
        priority = 0
        max_mentions_per_message = 1

    class _Cfg:
        mention = _Mention()

    monkeypatch.setattr(handlers.manager, "broadcast_to_room", _fake_broadcast)
    monkeypatch.setattr(handlers, "enqueue_task", _fake_enqueue)
    monkeypatch.setattr(handlers, "get_agent_settings", lambda: _Cfg())

    await handlers._trigger_mentions(
        room_id="room-1",
        source_message_id="msg-1",
        user=user,
        mentions=[" facilitator ", "UNKNOWN", "facilitator", ""],
    )

    statuses = [payload["status"] for _, payload in calls if payload["type"] == "agent:ack"]
    assert statuses == ["accepted"]
    assert any(payload["type"] == "agent:queued" for _, payload in calls)
    assert len(enqueued) == 1
    assert enqueued[0][1]["agent_role"] == "facilitator"


@pytest.mark.asyncio
async def test_handle_chat_message_broadcasts_and_triggers(monkeypatch):
    created_at = datetime.now(timezone.utc)
    msg = SimpleNamespace(
        id=uuid.uuid4(),
        seq_num=12,
        content="hello",
        created_at=created_at,
    )
    saved = {}
    broadcast_payloads = []
    triggered = {"mentions": None, "monopoly": None}

    async def _fake_save(_db, room_id, user_id, content, mentions):
        saved["room_id"] = room_id
        saved["user_id"] = user_id
        saved["content"] = content
        saved["mentions"] = mentions
        return msg

    async def _fake_broadcast(_room_id, payload):
        broadcast_payloads.append(payload)

    async def _fake_trigger_mentions(room_id, source_message_id, user, mentions):
        triggered["mentions"] = (room_id, source_message_id, user.display_name, mentions)

    async def _fake_check_monopoly(room_id, sender_id):
        triggered["monopoly"] = (room_id, sender_id)

    user = User(
        id=uuid.uuid4(),
        username="student_1",
        password_hash="x",
        display_name="Student 1",
        role=UserRole.student,
    )

    monkeypatch.setattr(handlers.MessageService, "save_student_message", _fake_save)
    monkeypatch.setattr(handlers.manager, "broadcast_to_room", _fake_broadcast)
    monkeypatch.setattr(handlers, "_trigger_mentions", _fake_trigger_mentions)
    monkeypatch.setattr(handlers.trigger_detector, "check_monopoly", _fake_check_monopoly)
    monkeypatch.setattr(handlers, "get_redis_client", lambda: (_ for _ in ()).throw(RuntimeError("redis down")))

    await handlers.handle_chat_message(
        data={"type": "chat:message", "content": "  hello  ", "mentions": ["facilitator"]},
        room_id="room-1",
        user=user,
        db=object(),
    )

    assert saved["content"] == "hello"
    assert saved["mentions"] == ["facilitator"]
    assert broadcast_payloads[0]["type"] == "chat:new_message"
    assert broadcast_payloads[0]["seq_num"] == 12
    assert triggered["mentions"][3] == ["facilitator"]
    assert triggered["monopoly"] == ("room-1", str(user.id))
