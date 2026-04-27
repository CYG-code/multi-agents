from __future__ import annotations

import time
from datetime import datetime, timezone
from uuid import UUID

from fastapi import Depends, WebSocket, WebSocketDisconnect
from jose import JWTError
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.queue import enqueue_task
from app.agents.role_agents import ROLE_AGENTS
from app.agents.settings import get_agent_settings
from app.analysis.triggers import trigger_detector
from app.db.redis_client import get_redis_client, touch_online_presence
from app.db.session import get_db
from app.models.room_member import RoomMember
from app.models.user import User
from app.schemas.message import ChatMessageFrame
from app.services.auth_service import decode_access_token
from app.services.message_service import MessageService
from app.services import writing_doc_service
from app.websocket.manager import ConnectionManager

manager = ConnectionManager()


async def verify_token(token: str, db: AsyncSession) -> User | None:
    try:
        payload = decode_access_token(token)
        user_id = payload.get("sub")
        if not user_id:
            return None
        parsed_id = UUID(user_id)
    except (JWTError, ValueError, TypeError):
        return None

    result = await db.execute(select(User).where(User.id == parsed_id))
    return result.scalar_one_or_none()


async def is_room_member(user_id: UUID, room_id: str, db: AsyncSession) -> bool:
    try:
        parsed_room_id = UUID(room_id)
    except ValueError:
        return False

    result = await db.execute(
        select(RoomMember.id).where(
            RoomMember.room_id == parsed_room_id,
            RoomMember.user_id == user_id,
        )
    )
    return result.scalar_one_or_none() is not None


def _normalized_mentions(mentions: list[str] | None) -> list[str]:
    if not mentions:
        return []

    cfg = get_agent_settings()
    max_mentions = max(1, cfg.mention.max_mentions_per_message)

    normalized = []
    seen = set()
    for raw in mentions:
        role = (raw or "").strip().lower()
        if not role or role in seen:
            continue
        seen.add(role)
        normalized.append(role)
        if len(normalized) >= max_mentions:
            break
    return normalized


async def _trigger_mentions(room_id: str, source_message_id: str, user: User, mentions: list[str] | None) -> None:
    cfg = get_agent_settings()
    if not cfg.mention.enabled:
        return

    for role in _normalized_mentions(mentions):
        if role not in ROLE_AGENTS:
            await manager.broadcast_to_room(
                room_id,
                {
                    "type": "agent:ack",
                    "agent_role": role,
                    "source_message_id": source_message_id,
                    "status": "unsupported",
                    "message": "当前版本暂不支持该智能体。",
                },
            )
            continue

        await manager.broadcast_to_room(
            room_id,
            {
                "type": "agent:ack",
                "agent_role": role,
                "source_message_id": source_message_id,
                "status": "accepted",
                "message": "已收到召唤。",
            },
        )

        task = await enqueue_task(
            room_id,
            {
                "room_id": room_id,
                "agent_role": role,
                "reason": f"学生 {user.display_name} 通过 @{role} 主动召唤。",
                "strategy": "优先回应该同学的提问，并给出可继续讨论的下一步。",
                "priority": cfg.mention.priority,
                "trigger_type": "mention",
                "student_name": user.display_name,
                "source_message_id": source_message_id,
                "triggered_at": time.time(),
            },
        )

        await manager.broadcast_to_room(
            room_id,
            {
                "type": "agent:queued",
                "agent_role": role,
                "source_message_id": source_message_id,
                "status": "queued",
                "task_id": task["task_id"],
                "message": "已进入处理队列。",
            },
        )


async def _touch_online_presence_best_effort(room_id: str, user_id: str) -> None:
    try:
        await touch_online_presence(room_id, user_id)
    except RuntimeError:
        pass


async def handle_chat_message(data: dict, room_id: str, user: User, db: AsyncSession) -> None:
    try:
        frame = ChatMessageFrame.model_validate(data)
    except ValidationError:
        return

    content = frame.content.strip()
    mentions = frame.mentions
    if not content:
        return

    msg = await MessageService.save_student_message(db, room_id, str(user.id), content, mentions)

    try:
        redis_client = get_redis_client()
    except RuntimeError:
        redis_client = None

    now_ts = msg.created_at.timestamp() if msg.created_at else None
    if redis_client is not None and now_ts is not None:
        await redis_client.set(f"room:{room_id}:last_msg_time", now_ts)
        await redis_client.set(f"room:{room_id}:last_activity_time", now_ts)
        await redis_client.setnx(f"room:{room_id}:start_time", now_ts)
        await redis_client.sadd("active_rooms", room_id)
    await _touch_online_presence_best_effort(room_id, str(user.id))

    await manager.broadcast_to_room(
        room_id,
        {
            "type": "chat:new_message",
            "id": str(msg.id),
            "seq_num": msg.seq_num,
            "sender_type": "student",
            "sender_id": str(user.id),
            "display_name": user.display_name,
            "content": msg.content,
            "created_at": msg.created_at.isoformat() if msg.created_at else None,
        },
    )

    await trigger_detector.check_monopoly(room_id, str(user.id))
    await _trigger_mentions(room_id, str(msg.id), user, mentions)


async def handle_writing_update(websocket: WebSocket, data: dict, room_id: str, user: User) -> None:
    content = str(data.get("content") or "")
    base_version_raw = data.get("base_version")
    try:
        base_version = int(base_version_raw) if base_version_raw is not None else None
    except (TypeError, ValueError):
        base_version = None
    # Soft guard to avoid extremely large payloads over websocket.
    if len(content) > 200_000:
        return

    state, applied = await writing_doc_service.apply_writing_doc_update_with_base_version(
        room_id,
        content,
        str(user.id),
        updated_by_display_name=user.display_name,
        base_version=base_version,
    )
    await _touch_online_presence_best_effort(room_id, str(user.id))
    if not applied:
        await websocket.send_json(
            {
                "type": "writing:resync",
                "room_id": room_id,
                "content": state["content"],
                "version": state["version"],
                "updated_at": state["updated_at"],
                "updated_by": state["updated_by"],
                "updated_by_display_name": state.get("updated_by_display_name"),
                "reason": "stale_base_version",
            }
        )
        return

    await manager.broadcast_to_room(
        room_id,
        {
            "type": "writing:updated",
            "room_id": room_id,
            "content": state["content"],
            "version": state["version"],
            "updated_at": state["updated_at"],
            "updated_by": state["updated_by"],
            "updated_by_display_name": state.get("updated_by_display_name"),
        },
    )


async def handle_writing_awareness(data: dict, room_id: str, user: User) -> None:
    await _touch_online_presence_best_effort(room_id, str(user.id))
    payload = {
        "type": "writing:awareness",
        "room_id": room_id,
        "user_id": str(user.id),
        "display_name": user.display_name,
        "is_editing": bool(data.get("is_editing")),
        "cursor": data.get("cursor"),
        "at": datetime.now(timezone.utc).isoformat(),
    }
    await manager.broadcast_to_room(room_id, payload)


async def websocket_endpoint(
    websocket: WebSocket,
    room_id: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    await websocket.accept()

    try:
        auth_data = await websocket.receive_json()
    except Exception:
        await websocket.close(code=4002, reason="Auth timeout")
        return

    if auth_data.get("type") != "auth":
        await websocket.close(code=4001, reason="First frame must be auth")
        return

    user = await verify_token(auth_data.get("token", ""), db)
    if not user:
        await websocket.close(code=4001, reason="Invalid token")
        return

    if not await is_room_member(user.id, room_id, db):
        await websocket.close(code=4003, reason="Not a room member")
        return

    await manager.connect(websocket, room_id, user)

    redis_client = get_redis_client()
    online_count = int(await redis_client.scard(f"room:{room_id}:online_users"))
    await manager.broadcast_to_room(
        room_id,
        {
            "type": "room:user_join",
            "user_id": str(user.id),
            "display_name": user.display_name,
            "online_count": online_count,
        },
    )

    try:
        while True:
            data = await websocket.receive_json()
            if data.get("type") == "presence:ping":
                await _touch_online_presence_best_effort(room_id, str(user.id))
                continue
            if data.get("type") == "chat:message":
                await handle_chat_message(data, room_id, user, db)
                continue
            if data.get("type") == "writing:update":
                await handle_writing_update(websocket, data, room_id, user)
                continue
            if data.get("type") == "writing:awareness":
                await handle_writing_awareness(data, room_id, user)
    except WebSocketDisconnect:
        await manager.disconnect(websocket, room_id, str(user.id))
        online_count = int(await redis_client.scard(f"room:{room_id}:online_users"))
        await manager.broadcast_to_room(
            room_id,
            {
                "type": "room:user_leave",
                "user_id": str(user.id),
                "display_name": user.display_name,
                "online_count": online_count,
            },
        )
