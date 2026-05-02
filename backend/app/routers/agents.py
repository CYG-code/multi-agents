from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.redis_client import get_redis_client
from app.db.session import get_db
from app.dependencies import get_current_user
from app.models.room_member import RoomMember
from app.models.user import User, UserRole

router = APIRouter()

_TASK_FIELDS = [
    "task_id",
    "room_id",
    "agent_role",
    "trigger_type",
    "status",
    "reason",
    "source_message_id",
    "created_at",
    "queued_at",
    "running_at",
    "finished_at",
    "error",
    "drop_reason",
]


async def _can_view_task(db: AsyncSession, current_user: User, room_id: str | None) -> bool:
    if current_user.role == UserRole.teacher:
        return True
    if not room_id:
        return False
    try:
        parsed_room_id = UUID(str(room_id))
    except (TypeError, ValueError):
        return False

    result = await db.execute(
        select(RoomMember.id).where(
            RoomMember.room_id == parsed_room_id,
            RoomMember.user_id == current_user.id,
        )
    )
    return result.scalar_one_or_none() is not None


@router.get("/tasks/{task_id}")
async def get_agent_task_status(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    redis_client = get_redis_client()
    key = f"agent:task:{task_id}"
    data = await redis_client.hgetall(key)
    if not data:
        raise HTTPException(status_code=404, detail="Agent task not found")

    normalized = {str(k): str(v) for k, v in data.items()}
    room_id = normalized.get("room_id") or None
    if not await _can_view_task(db, current_user, room_id):
        raise HTTPException(status_code=403, detail="Not authorized to view this agent task")

    return {field: normalized.get(field, "") for field in _TASK_FIELDS}
