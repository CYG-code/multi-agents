from __future__ import annotations

import os
import random
import time
import traceback
from datetime import datetime, timezone
from uuid import UUID

from fastapi import WebSocket, WebSocketDisconnect
from jose import JWTError
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.agent_messages import (
    MENTION_ACCEPTED,
    MENTION_QUEUED,
    MENTION_REASON_TEMPLATE,
    MENTION_STRATEGY,
    MENTION_UNSUPPORTED,
)
from app.agents.queue import enqueue_task
from app.agents.queue import queue_key
from app.agents.role_agents import ROLE_AGENTS
from app.agents.settings import get_agent_settings
from app.analysis.triggers import trigger_detector
from app.db.redis_client import get_redis_client, touch_online_presence
from app.db.redis_client import get_user_active_session_jti
from app.db.session import AsyncSessionLocal
from app.models.room_member import RoomMember
from app.models.user import User
from app.schemas.message import ChatMessageFrame
from app.services.auth_service import decode_access_token
from app.services.message_service import MessageService
from app.services import writing_doc_service
from app.websocket.manager import manager

WS_DEBUG_LOG = os.getenv("WS_DEBUG_LOG", "").lower() == "true"


def _short_jti(session_jti: str | None) -> str | None:
    if not session_jti:
        return None
    return str(session_jti)[:8]


def _new_connection_id() -> str:
    return f"ws-{int(time.time() * 1000) % 10000000}-{random.randint(1000, 9999)}"


def log_ws_debug(
    event: str,
    room_id: str,
    connection_id: str,
    user_id: str | None = None,
    username: str | None = None,
    session_jti: str | None = None,
    extra: dict | None = None,
) -> None:
    if not WS_DEBUG_LOG:
        return
    payload = {
        "event": event,
        "ts": datetime.now(timezone.utc).isoformat(),
        "room_id": room_id,
        "connection_id": connection_id,
        "user_id": user_id,
        "username": username,
        "session_jti": _short_jti(session_jti),
    }
    if extra:
        payload["extra"] = extra
    print("[WS-DEBUG]", payload, flush=True)


async def verify_token(token: str | None, db: AsyncSession) -> tuple[User, str] | None:
    if not isinstance(token, str) or not token.strip():
        return None
    try:
        payload = decode_access_token(token)
        user_id = payload.get("sub")
        token_jti = payload.get("jti")
        if not user_id:
            return None
        if not token_jti:
            return None
        parsed_id = UUID(user_id)
    except (JWTError, ValueError, TypeError, AttributeError):
        return None

    try:
        active_jti = await get_user_active_session_jti(user_id)
        if active_jti and active_jti != token_jti:
            return None
    except RuntimeError:
        # Redis unavailable: keep backward-compatible behavior.
        pass

    result = await db.execute(select(User).where(User.id == parsed_id))
    user = result.scalar_one_or_none()
    if user is None:
        return None
    return user, token_jti


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
                "target_dimension": "user_request",
                "evidence": [],
                "current_phase": "unknown",
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


async def _is_agent_pipeline_busy(room_id: str) -> bool:
    try:
        redis_client = get_redis_client()
    except RuntimeError:
        return False

    try:
        if await redis_client.exists(f"room:{room_id}:agent_lock"):
            return True
        pending = int(await redis_client.zcard(queue_key(room_id)))
        return pending > 0
    except Exception:
        return False


async def _first_cooling_mention_role(room_id: str, mentions: list[str] | None) -> str | None:
    normalized_mentions = _normalized_mentions(mentions)
    if not normalized_mentions:
        return None
    try:
        redis_client = get_redis_client()
    except RuntimeError:
        return None
    for role in normalized_mentions:
        try:
            if await redis_client.exists(f"cooldown:{room_id}:{role}"):
                return role
        except Exception:
            continue
    return None


async def _cooldown_remaining_seconds(room_id: str, role: str) -> int:
    try:
        redis_client = get_redis_client()
    except RuntimeError:
        return 1
    try:
        ttl = await redis_client.ttl(f"cooldown:{room_id}:{role}")
        if isinstance(ttl, int) and ttl > 0:
            return ttl
    except Exception:
        pass
    return 1


async def handle_chat_message(
    data: dict,
    room_id: str,
    user: User,
    db: AsyncSession,
    websocket: WebSocket | None = None,
) -> None:
    try:
        frame = ChatMessageFrame.model_validate(data)
    except ValidationError:
        return

    content = frame.content.strip()
    mentions = frame.mentions
    if not content:
        return
    cooling_role = await _first_cooling_mention_role(room_id, mentions)
    if cooling_role:
        remaining_seconds = await _cooldown_remaining_seconds(room_id, cooling_role)
        if websocket is not None:
            await websocket.send_json(
                {
                    "type": "agent:mention_blocked",
                    "reason": "agent_cooling",
                    "agent_role": cooling_role,
                    "message": f"???????????? {remaining_seconds} ?????",
                }
            )
        return

    normalized_mentions = _normalized_mentions(mentions)
    if normalized_mentions and await _is_agent_pipeline_busy(room_id):
        if websocket is not None:
            await websocket.send_json(
                {
                    "type": "agent:mention_blocked",
                    "reason": "agent_busy",
                    "message": "?????????????????? @ ???",
                }
            )
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
) -> None:
    connection_id = _new_connection_id()
    user: User | None = None
    session_jti: str | None = None
    redis_client = None
    manager_connected = False

    log_ws_debug("ws_accept_start", room_id, connection_id)
    await websocket.accept()
    log_ws_debug("ws_accept_done", room_id, connection_id)

    log_ws_debug("auth_frame_wait_start", room_id, connection_id)
    try:
        auth_data = await websocket.receive_json()
        log_ws_debug("auth_frame_received", room_id, connection_id, extra={"frame_type": auth_data.get("type")})
    except WebSocketDisconnect:
        log_ws_debug("websocket_disconnect", room_id, connection_id, extra={"stage": "auth_frame_wait"})
        return
    except Exception as exc:
        log_ws_debug(
            "unexpected_exception",
            room_id,
            connection_id,
            extra={
                "stage": "auth_frame_wait",
                "exception_class": type(exc).__name__,
                "exception_message": str(exc),
                "traceback": traceback.format_exc(limit=3),
            },
        )
        try:
            await websocket.close(code=4002, reason="Auth timeout")
        except RuntimeError:
            # Client already gone during handshake.
            pass
        return

    if auth_data.get("type") != "auth":
        log_ws_debug("auth_token_invalid", room_id, connection_id, extra={"reason": "first_frame_not_auth"})
        try:
            await websocket.close(code=4001, reason="First frame must be auth")
        except RuntimeError:
            pass
        return

    log_ws_debug("auth_token_verify_start", room_id, connection_id)
    log_ws_debug("db_session_open", room_id, connection_id, extra={"stage": "auth"})
    async with AsyncSessionLocal() as db:
        verified = await verify_token(auth_data.get("token", ""), db)
        if not verified:
            log_ws_debug("db_session_closed", room_id, connection_id, extra={"stage": "auth"})
            log_ws_debug("auth_token_invalid", room_id, connection_id, extra={"reason": "token_verify_failed"})
            try:
                await websocket.close(code=4001, reason="Invalid token")
            except RuntimeError:
                pass
            return
        user, session_jti = verified
        log_ws_debug(
            "auth_token_verified",
            room_id,
            connection_id,
            user_id=str(user.id),
            username=user.display_name,
            session_jti=session_jti,
        )

        log_ws_debug(
            "room_member_check_start",
            room_id,
            connection_id,
            user_id=str(user.id),
            username=user.display_name,
            session_jti=session_jti,
        )
        if not await is_room_member(user.id, room_id, db):
            log_ws_debug("db_session_closed", room_id, connection_id, extra={"stage": "auth"})
            log_ws_debug(
                "room_member_forbidden",
                room_id,
                connection_id,
                user_id=str(user.id),
                username=user.display_name,
                session_jti=session_jti,
            )
            try:
                await websocket.close(code=4003, reason="Not a room member")
            except RuntimeError:
                pass
            return
    log_ws_debug("db_session_closed", room_id, connection_id, extra={"stage": "auth"})
    log_ws_debug(
        "room_member_checked",
        room_id,
        connection_id,
        user_id=str(user.id),
        username=user.display_name,
        session_jti=session_jti,
    )

    log_ws_debug(
        "manager_connect_start",
        room_id,
        connection_id,
        user_id=str(user.id),
        username=user.display_name,
        session_jti=session_jti,
    )
    await manager.connect(websocket, room_id, user, session_jti=session_jti)
    manager_connected = True
    log_ws_debug(
        "manager_connect_done",
        room_id,
        connection_id,
        user_id=str(user.id),
        username=user.display_name,
        session_jti=session_jti,
    )

    redis_client = get_redis_client()
    log_ws_debug(
        "room_user_join_broadcast_start",
        room_id,
        connection_id,
        user_id=str(user.id),
        username=user.display_name,
        session_jti=session_jti,
    )
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
    log_ws_debug(
        "room_user_join_broadcast_done",
        room_id,
        connection_id,
        user_id=str(user.id),
        username=user.display_name,
        session_jti=session_jti,
        extra={"online_count": online_count},
    )

    try:
        log_ws_debug(
            "receive_loop_start",
            room_id,
            connection_id,
            user_id=str(user.id),
            username=user.display_name,
            session_jti=session_jti,
        )
        while True:
            data = await websocket.receive_json()
            if data.get("type") == "presence:ping":
                log_ws_debug(
                    "presence_ping_received",
                    room_id,
                    connection_id,
                    user_id=str(user.id),
                    username=user.display_name,
                    session_jti=session_jti,
                )
                await _touch_online_presence_best_effort(room_id, str(user.id))
                continue
            if data.get("type") == "chat:message":
                log_ws_debug(
                    "db_session_open",
                    room_id,
                    connection_id,
                    user_id=str(user.id),
                    username=user.display_name,
                    session_jti=session_jti,
                    extra={"stage": "chat_message"},
                )
                async with AsyncSessionLocal() as db:
                    await handle_chat_message(data, room_id, user, db, websocket=websocket)
                log_ws_debug(
                    "db_session_closed",
                    room_id,
                    connection_id,
                    user_id=str(user.id),
                    username=user.display_name,
                    session_jti=session_jti,
                    extra={"stage": "chat_message"},
                )
                continue
            if data.get("type") == "writing:update":
                await handle_writing_update(websocket, data, room_id, user)
                continue
            if data.get("type") == "writing:awareness":
                await handle_writing_awareness(data, room_id, user)
    except WebSocketDisconnect:
        log_ws_debug(
            "websocket_disconnect",
            room_id,
            connection_id,
            user_id=str(user.id),
            username=user.display_name,
            session_jti=session_jti,
            extra={"stage": "receive_loop"},
        )
    except RuntimeError as exc:
        # Starlette may raise RuntimeError instead of WebSocketDisconnect on closed sockets.
        if "WebSocket is not connected" not in str(exc):
            log_ws_debug(
                "runtime_error",
                room_id,
                connection_id,
                user_id=str(user.id) if user else None,
                username=user.display_name if user else None,
                session_jti=session_jti,
                extra={
                    "exception_class": type(exc).__name__,
                    "exception_message": str(exc),
                    "traceback": traceback.format_exc(limit=3),
                },
            )
            raise
        log_ws_debug(
            "runtime_error",
            room_id,
            connection_id,
            user_id=str(user.id),
            username=user.display_name,
            session_jti=session_jti,
            extra={
                "exception_class": type(exc).__name__,
                "exception_message": str(exc),
                "traceback": traceback.format_exc(limit=3),
            },
        )
    except Exception as exc:
        log_ws_debug(
            "unexpected_exception",
            room_id,
            connection_id,
            user_id=str(user.id) if user else None,
            username=user.display_name if user else None,
            session_jti=session_jti,
            extra={
                "exception_class": type(exc).__name__,
                "exception_message": str(exc),
                "traceback": traceback.format_exc(limit=3),
            },
        )
        raise
    finally:
        if user and manager_connected:
            log_ws_debug(
                "manager_disconnect_start",
                room_id,
                connection_id,
                user_id=str(user.id),
                username=user.display_name,
                session_jti=session_jti,
            )
            await manager.disconnect(websocket, room_id, str(user.id), session_jti=session_jti)
            log_ws_debug(
                "manager_disconnect_done",
                room_id,
                connection_id,
                user_id=str(user.id),
                username=user.display_name,
                session_jti=session_jti,
            )
            if redis_client is None:
                redis_client = get_redis_client()
            log_ws_debug(
                "room_user_leave_broadcast_start",
                room_id,
                connection_id,
                user_id=str(user.id),
                username=user.display_name,
                session_jti=session_jti,
            )
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
            log_ws_debug(
                "room_user_leave_broadcast_done",
                room_id,
                connection_id,
                user_id=str(user.id),
                username=user.display_name,
                session_jti=session_jti,
                extra={"online_count": online_count},
            )
