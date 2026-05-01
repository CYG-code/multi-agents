import os
import time
import traceback
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.redis_client import get_redis_client
from app.models.message import Message, MessageStatus, SenderType
from app.models.user import User

WS_DEBUG_LOG = os.getenv("WS_DEBUG_LOG", "").lower() == "true"


def _msg_log(event: str, room_id: str, user_id: str | None = None, extra: dict | None = None) -> None:
    if not WS_DEBUG_LOG:
        return
    payload = {
        "event": event,
        "ts": datetime.now(timezone.utc).isoformat(),
        "room_id": room_id,
        "user_id": user_id,
    }
    if extra:
        payload["extra"] = extra
    print("[MSG-SVC-DEBUG]", payload, flush=True)


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
        started = time.perf_counter()
        _msg_log("get_next_seq_start", room_id)
        redis_client = get_redis_client()
        seq = int(await redis_client.incr(f"room:{room_id}:msg_seq"))
        _msg_log(
            "get_next_seq_done",
            room_id,
            extra={"duration_ms": round((time.perf_counter() - started) * 1000, 3), "seq_num": seq},
        )
        return seq

    @staticmethod
    async def save_student_message(
        db: AsyncSession,
        room_id: str,
        user_id: str,
        content: str,
        mentions: list[str] | None = None,
        connection_id: str | None = None,
        loadmsg_id: str | None = None,
    ) -> Message:
        _ = mentions  # reserved for P3 mention-triggered workflows
        total_started = time.perf_counter()
        try:
            seq_num = await MessageService.get_next_seq_num(room_id)

            _msg_log(
                "db_insert_start",
                room_id,
                user_id=user_id,
                extra={"seq_num": seq_num, "connection_id": connection_id, "loadmsg_id": loadmsg_id},
            )
            msg = Message(
                room_id=room_id,
                seq_num=seq_num,
                sender_type=SenderType.student,
                sender_id=user_id,
                content=content,
                status=MessageStatus.ok,
            )
            db.add(msg)

            commit_started = time.perf_counter()
            _msg_log(
                "db_commit_start",
                room_id,
                user_id=user_id,
                extra={"seq_num": seq_num, "connection_id": connection_id, "loadmsg_id": loadmsg_id},
            )
            await db.commit()
            _msg_log(
                "db_commit_done",
                room_id,
                user_id=user_id,
                extra={
                    "seq_num": seq_num,
                    "connection_id": connection_id,
                    "loadmsg_id": loadmsg_id,
                    "duration_ms": round((time.perf_counter() - commit_started) * 1000, 3),
                },
            )

            refresh_started = time.perf_counter()
            _msg_log(
                "db_refresh_start",
                room_id,
                user_id=user_id,
                extra={"seq_num": seq_num, "connection_id": connection_id, "loadmsg_id": loadmsg_id},
            )
            await db.refresh(msg)
            _msg_log(
                "db_refresh_done",
                room_id,
                user_id=user_id,
                extra={
                    "seq_num": seq_num,
                    "connection_id": connection_id,
                    "loadmsg_id": loadmsg_id,
                    "duration_ms": round((time.perf_counter() - refresh_started) * 1000, 3),
                },
            )
            _msg_log(
                "save_student_message_done",
                room_id,
                user_id=user_id,
                extra={
                    "seq_num": seq_num,
                    "connection_id": connection_id,
                    "loadmsg_id": loadmsg_id,
                    "duration_ms": round((time.perf_counter() - total_started) * 1000, 3),
                },
            )
            return msg
        except Exception as exc:
            _msg_log(
                "save_student_message_error",
                room_id,
                user_id=user_id,
                extra={
                    "exception_class": type(exc).__name__,
                    "exception_message": str(exc),
                    "connection_id": connection_id,
                    "loadmsg_id": loadmsg_id,
                    "duration_ms": round((time.perf_counter() - total_started) * 1000, 3),
                    "traceback": traceback.format_exc(limit=3),
                },
            )
            raise

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
