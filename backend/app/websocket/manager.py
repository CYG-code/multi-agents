import asyncio
import json
import os
import traceback
from datetime import datetime, timezone

from fastapi import WebSocket

from app.db.redis_client import get_redis_client, touch_online_presence

WS_DEBUG_LOG = os.getenv("WS_DEBUG_LOG", "").lower() == "true"


def _short_jti(session_jti: str | None) -> str | None:
    if not session_jti:
        return None
    return str(session_jti)[:8]


def _manager_log(
    event: str,
    room_id: str | None = None,
    user_id: str | None = None,
    session_jti: str | None = None,
    extra: dict | None = None,
) -> None:
    if not WS_DEBUG_LOG:
        return
    payload = {
        "event": event,
        "ts": datetime.now(timezone.utc).isoformat(),
        "room_id": room_id,
        "user_id": user_id,
        "session_jti": _short_jti(session_jti),
    }
    if extra:
        payload["extra"] = extra
    print("[WS-MANAGER-DEBUG]", payload, flush=True)


class ConnectionManager:
    def __init__(self):
        self._rooms: dict[str, list[dict]] = {}
        self._subscribers: dict[str, asyncio.Task] = {}
        self._user_connections: dict[str, dict[str, set[WebSocket]]] = {}

    async def connect(self, websocket: WebSocket, room_id: str, user, session_jti: str | None = None) -> None:
        user_id = str(user.id)
        _manager_log(
            "connect_start",
            room_id=room_id,
            user_id=user_id,
            session_jti=session_jti,
            extra={"rooms_count": len(self._rooms), "room_conn_count": len(self._rooms.get(room_id, []))},
        )

        if room_id not in self._rooms:
            _manager_log(
                "connect_room_init",
                room_id=room_id,
                user_id=user_id,
                session_jti=session_jti,
                extra={"rooms_count_before": len(self._rooms)},
            )
            self._rooms[room_id] = []
            self._subscribers[room_id] = asyncio.create_task(self._redis_subscriber(room_id))
            _manager_log(
                "redis_subscriber_task_created",
                room_id=room_id,
                user_id=user_id,
                session_jti=session_jti,
                extra={"subscribers_count": len(self._subscribers)},
            )

        self._rooms[room_id].append(
            {
                "ws": websocket,
                "user_id": user_id,
                "session_jti": session_jti or "",
                "role": getattr(user.role, "value", str(user.role)),
            }
        )
        if session_jti:
            self._user_connections.setdefault(user_id, {}).setdefault(session_jti, set()).add(websocket)

        redis_client = get_redis_client()
        user_conn_key = f"room:{room_id}:online_user_conn_counts"
        online_users_key = f"room:{room_id}:online_users"

        _manager_log(
            "redis_presence_update_start",
            room_id=room_id,
            user_id=user_id,
            session_jti=session_jti,
            extra={"room_conn_count": len(self._rooms.get(room_id, []))},
        )
        user_conn_count = int(await redis_client.hincrby(user_conn_key, user_id, 1))
        if user_conn_count == 1:
            await redis_client.sadd(online_users_key, user_id)
        await touch_online_presence(room_id, user_id)
        _manager_log(
            "redis_presence_update_done",
            room_id=room_id,
            user_id=user_id,
            session_jti=session_jti,
            extra={"user_conn_count": user_conn_count},
        )

        _manager_log(
            "connect_done",
            room_id=room_id,
            user_id=user_id,
            session_jti=session_jti,
            extra={
                "rooms_count": len(self._rooms),
                "room_conn_count": len(self._rooms.get(room_id, [])),
            },
        )

    async def disconnect(self, websocket: WebSocket, room_id: str, user_id: str, session_jti: str | None = None) -> None:
        _manager_log(
            "disconnect_start",
            room_id=room_id,
            user_id=user_id,
            session_jti=session_jti,
            extra={"rooms_count": len(self._rooms), "room_conn_count": len(self._rooms.get(room_id, []))},
        )

        if room_id in self._rooms:
            self._rooms[room_id] = [c for c in self._rooms[room_id] if c["ws"] != websocket]
            if not self._rooms[room_id]:
                task = self._subscribers.pop(room_id, None)
                if task is not None:
                    task.cancel()
                del self._rooms[room_id]

        if session_jti and user_id in self._user_connections:
            jti_map = self._user_connections[user_id]
            ws_set = jti_map.get(session_jti)
            if ws_set is not None:
                ws_set.discard(websocket)
                if not ws_set:
                    jti_map.pop(session_jti, None)
            if not jti_map:
                self._user_connections.pop(user_id, None)

        redis_client = get_redis_client()
        user_conn_key = f"room:{room_id}:online_user_conn_counts"
        online_users_key = f"room:{room_id}:online_users"

        _manager_log(
            "disconnect_presence_update_start",
            room_id=room_id,
            user_id=user_id,
            session_jti=session_jti,
            extra={"room_conn_count": len(self._rooms.get(room_id, []))},
        )
        user_conn_count = int(await redis_client.hincrby(user_conn_key, user_id, -1))
        if user_conn_count <= 0:
            await redis_client.hdel(user_conn_key, user_id)
            await redis_client.srem(online_users_key, user_id)
            await redis_client.hdel(f"room:{room_id}:online_user_last_seen", user_id)

        _manager_log(
            "disconnect_presence_update_done",
            room_id=room_id,
            user_id=user_id,
            session_jti=session_jti,
            extra={"user_conn_count": user_conn_count},
        )
        _manager_log(
            "disconnect_done",
            room_id=room_id,
            user_id=user_id,
            session_jti=session_jti,
            extra={"rooms_count": len(self._rooms), "room_conn_count": len(self._rooms.get(room_id, []))},
        )

    async def revoke_user_session(self, user_id: str, session_jti: str, payload: dict | None = None) -> None:
        jti_map = self._user_connections.get(user_id) or {}
        targets = list(jti_map.get(session_jti) or [])
        if not targets:
            return

        msg = payload or {
            "type": "auth:session_revoked",
            "reason": "logged_in_elsewhere",
        }
        for ws in targets:
            try:
                await ws.send_json(msg)
            except Exception:
                continue

    async def broadcast_to_room(self, room_id: str, data: dict) -> None:
        redis_client = get_redis_client()
        _manager_log(
            "broadcast_publish_start",
            room_id=room_id,
            extra={"payload_type": data.get("type"), "rooms_count": len(self._rooms)},
        )
        await redis_client.publish(f"room:{room_id}", json.dumps(data, ensure_ascii=False))
        _manager_log(
            "broadcast_publish_done",
            room_id=room_id,
            extra={"payload_type": data.get("type")},
        )

    async def _redis_subscriber(self, room_id: str) -> None:
        redis_client = get_redis_client()
        pubsub = redis_client.pubsub()
        await pubsub.subscribe(f"room:{room_id}")
        _manager_log("redis_subscriber_start", room_id=room_id)

        try:
            async for message in pubsub.listen():
                if message.get("type") != "message":
                    continue

                data = json.loads(message["data"])
                if room_id not in self._rooms:
                    continue

                for conn in list(self._rooms[room_id]):
                    try:
                        _manager_log(
                            "send_json_start",
                            room_id=room_id,
                            user_id=conn.get("user_id"),
                            session_jti=conn.get("session_jti"),
                            extra={"payload_type": data.get("type")},
                        )
                        await conn["ws"].send_json(data)
                    except Exception as exc:
                        _manager_log(
                            "send_json_error",
                            room_id=room_id,
                            user_id=conn.get("user_id"),
                            session_jti=conn.get("session_jti"),
                            extra={
                                "payload_type": data.get("type"),
                                "exception_class": type(exc).__name__,
                                "exception_message": str(exc),
                                "traceback": traceback.format_exc(limit=3),
                            },
                        )
                        continue
        except asyncio.CancelledError:
            _manager_log("redis_subscriber_cancelled", room_id=room_id)
        except Exception as exc:
            _manager_log(
                "redis_subscriber_error",
                room_id=room_id,
                extra={
                    "exception_class": type(exc).__name__,
                    "exception_message": str(exc),
                    "traceback": traceback.format_exc(limit=3),
                },
            )
        finally:
            await pubsub.unsubscribe(f"room:{room_id}")
            await pubsub.aclose()
            _manager_log("redis_subscriber_closed", room_id=room_id)


manager = ConnectionManager()
