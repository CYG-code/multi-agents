import uuid

import pytest

from app.models.message import Message, MessageStatus, SenderType
from app.services.message_service import MessageService
from tests.mocks.mock_redis import MockRedis


@pytest.mark.asyncio
async def test_get_next_seq_num(monkeypatch):
    redis = MockRedis()
    monkeypatch.setattr("app.services.message_service.get_redis_client", lambda: redis)

    n1 = await MessageService.get_next_seq_num("room-1")
    n2 = await MessageService.get_next_seq_num("room-1")

    assert n1 == 1
    assert n2 == 2


def test_serialize_message():
    msg = Message(
        id=uuid.uuid4(),
        room_id=uuid.uuid4(),
        seq_num=3,
        sender_type=SenderType.student,
        sender_id=uuid.uuid4(),
        content="hello",
        status=MessageStatus.ok,
    )

    data = MessageService.serialize_message(msg, display_name="Alice")

    assert data["seq_num"] == 3
    assert data["sender_type"] == "student"
    assert data["display_name"] == "Alice"
    assert data["status"] == "ok"

