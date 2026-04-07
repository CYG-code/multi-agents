import asyncio
from uuid import UUID

from fastapi import Depends, WebSocket, WebSocketDisconnect
from jose import JWTError
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.redis_client import get_redis_client
from app.db.session import get_db
from app.models.room_member import RoomMember
from app.models.user import User
from app.schemas.message import ChatMessageFrame
from app.services.auth_service import decode_access_token
from app.services.message_service import MessageService
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


async def websocket_endpoint(
    websocket: WebSocket,
    room_id: str,
    db: AsyncSession = Depends(get_db),
):
    await websocket.accept()

    try:
        auth_data = await asyncio.wait_for(websocket.receive_json(), timeout=10.0)
    except asyncio.TimeoutError:
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
            if data.get("type") == "chat:message":
                await handle_chat_message(data, room_id, user, db)
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
