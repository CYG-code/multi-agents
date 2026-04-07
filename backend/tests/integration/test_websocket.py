import uuid

import pytest

from app.models.user import User, UserRole
from app.websocket.handlers import handle_chat_message


@pytest.mark.asyncio
async def test_handle_chat_message_broadcasts(monkeypatch):
    calls = {"saved": False, "broadcast": False}

    async def _mock_save(_db, _room_id, _user_id, content, _mentions):
        calls["saved"] = True

        class _Msg:
            def __init__(self, text: str):
                self.id = uuid.uuid4()
                self.seq_num = 10
                self.content = text
                self.created_at = None

        return _Msg(content)

    async def _mock_broadcast(_room_id, payload):
        calls["broadcast"] = True
        assert payload["type"] == "chat:new_message"
        assert payload["content"] == "hello"

    monkeypatch.setattr(
        "app.websocket.handlers.MessageService.save_student_message",
        _mock_save,
    )
    monkeypatch.setattr("app.websocket.handlers.manager.broadcast_to_room", _mock_broadcast)

    user = User(
        id=uuid.uuid4(),
        username="student_1",
        password_hash="x",
        display_name="Student 1",
        role=UserRole.student,
    )

    await handle_chat_message(
        data={"type": "chat:message", "content": "hello", "mentions": []},
        room_id="room-1",
        user=user,
        db=object(),
    )

    assert calls["saved"] is True
    assert calls["broadcast"] is True
