import asyncio
import json

from fastapi import WebSocket

from app.db.redis_client import get_redis_client, touch_online_presence


class ConnectionManager:
    def __init__(self):
        self._rooms: dict[str, list[dict]] = {}
        self._subscribers: dict[str, asyncio.Task] = {}
        self._user_connections: dict[str, dict[str, set[WebSocket]]] = {}

    async def connect(self, websocket: WebSocket, room_id: str, user, session_jti: str | None = None) -> None:
        if room_id not in self._rooms:
            self._rooms[room_id] = []
            self._subscribers[room_id] = asyncio.create_task(self._redis_subscriber(room_id))

        user_id = str(user.id)
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

        user_conn_count = int(await redis_client.hincrby(user_conn_key, user_id, 1))
        if user_conn_count == 1:
            await redis_client.sadd(online_users_key, user_id)
        await touch_online_presence(room_id, user_id)

    async def disconnect(self, websocket: WebSocket, room_id: str, user_id: str, session_jti: str | None = None) -> None:
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

        user_conn_count = int(await redis_client.hincrby(user_conn_key, user_id, -1))
        if user_conn_count <= 0:
            await redis_client.hdel(user_conn_key, user_id)
            await redis_client.srem(online_users_key, user_id)
            await redis_client.hdel(f"room:{room_id}:online_user_last_seen", user_id)

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
        await redis_client.publish(f"room:{room_id}", json.dumps(data, ensure_ascii=False))

    async def _redis_subscriber(self, room_id: str) -> None:
        redis_client = get_redis_client()
        pubsub = redis_client.pubsub()
        await pubsub.subscribe(f"room:{room_id}")

        try:
            async for message in pubsub.listen():
                if message.get("type") != "message":
                    continue

                data = json.loads(message["data"])
                if room_id not in self._rooms:
                    continue

                for conn in list(self._rooms[room_id]):
                    try:
                        await conn["ws"].send_json(data)
                    except Exception:
                        continue
        except asyncio.CancelledError:
            pass
        finally:
            await pubsub.unsubscribe(f"room:{room_id}")
            await pubsub.aclose()


manager = ConnectionManager()
