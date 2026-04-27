from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.redis_client import get_redis_client
from app.models.message import Message, MessageStatus, SenderType
from app.models.user import User


class MessageService:
    @staticmethod
    def serialize_message(message: Message, display_name: str | None = None) -> dict[str, Any]:
        return {
            "id": str(message.id),
            "room_id": str(message.room_id),
            "seq_num": message.seq_num,
            "sender_type": message.sender_type.value,
            "sender_id": str(message.sender_id) if message.sender_id else None,
            "source_message_id": str(message.source_message_id) if message.source_message_id else None,
            "display_name": display_name,
            "source_display_name_snapshot": message.source_display_name_snapshot,
            "agent_role": message.agent_role,
            "source_content_preview_snapshot": message.source_content_preview_snapshot,
            "content": message.content,
            "status": message.status.value,
            "created_at": message.created_at.isoformat() if message.created_at else None,
        }

    @staticmethod
    async def get_next_seq_num(room_id: str) -> int:
        redis_client = get_redis_client()
        return int(await redis_client.incr(f"room:{room_id}:msg_seq"))

    @staticmethod
    async def save_student_message(
        db: AsyncSession,
        room_id: str,
        user_id: str,
        content: str,
        mentions: list[str] | None = None,
    ) -> Message:
        _ = mentions  # reserved for P3 mention-triggered workflows
        seq_num = await MessageService.get_next_seq_num(room_id)

        msg = Message(
            room_id=room_id,
            seq_num=seq_num,
            sender_type=SenderType.student,
            sender_id=user_id,
            content=content,
            status=MessageStatus.ok,
        )
        db.add(msg)
        await db.commit()
        await db.refresh(msg)
        return msg

    @staticmethod
    async def get_history_messages(
        db: AsyncSession,
        room_id: str,
        before_seq: int | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        query = select(Message).where(Message.room_id == room_id)
        if before_seq is not None:
            query = query.where(Message.seq_num < before_seq)

        query = query.order_by(Message.seq_num.desc()).limit(limit + 1)
        result = await db.execute(query)
        messages = list(result.scalars().all())

        has_more = len(messages) > limit
        messages = messages[:limit]
        messages.reverse()

        sender_ids = {message.sender_id for message in messages if message.sender_id is not None}
        display_name_map: dict[Any, str] = {}
        if sender_ids:
            user_result = await db.execute(
                select(User.id, User.display_name).where(User.id.in_(sender_ids))
            )
            display_name_map = {row.id: row.display_name for row in user_result}

        oldest_seq = messages[0].seq_num if messages else None

        return {
            "messages": [
                MessageService.serialize_message(
                    message,
                    display_name=display_name_map.get(message.sender_id),
                )
                for message in messages
            ],
            "has_more": has_more,
            "oldest_seq": oldest_seq,
        }
