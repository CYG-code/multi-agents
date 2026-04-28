from uuid import UUID
from typing import Optional
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.message import Message
from app.models.room import Room, RoomStatus
from app.models.room_member import RoomMember
from app.schemas.room import RoomCreate


async def create_room(db: AsyncSession, data: RoomCreate, user_id: UUID) -> Room:
    room = Room(name=data.name, task_id=data.task_id, created_by=user_id)
    db.add(room)
    await db.commit()
    await db.refresh(room)
    return room


async def get_rooms(db: AsyncSession, status: Optional[str] = None) -> list[Room]:
    stmt = select(Room)
    if status:
        stmt = stmt.where(Room.status == status)
    else:
        stmt = stmt.where(Room.status != RoomStatus.ended)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_room(db: AsyncSession, room_id: UUID) -> Optional[Room]:
    result = await db.execute(select(Room).where(Room.id == room_id))
    return result.scalar_one_or_none()


async def join_room(db: AsyncSession, room_id: UUID, user_id: UUID) -> None:
    from sqlalchemy.dialects.postgresql import insert
    stmt = insert(RoomMember).values(room_id=room_id, user_id=user_id)
    stmt = stmt.on_conflict_do_nothing(index_elements=["room_id", "user_id"])
    await db.execute(stmt)
    await db.commit()


async def leave_room(db: AsyncSession, room_id: UUID, user_id: UUID) -> None:
    await db.execute(
        delete(RoomMember).where(
            RoomMember.room_id == room_id,
            RoomMember.user_id == user_id,
        )
    )
    await db.commit()


async def get_member_ids(db: AsyncSession, room_id: UUID) -> list[str]:
    result = await db.execute(select(RoomMember.user_id).where(RoomMember.room_id == room_id))
    return [str(row.user_id) for row in result.fetchall()]


async def get_member_count(db: AsyncSession, room_id: UUID) -> int:
    result = await db.execute(
        select(func.count()).where(RoomMember.room_id == room_id)
    )
    return result.scalar_one()


async def update_room_status(db: AsyncSession, room: Room, status: RoomStatus) -> Room:
    room.status = status
    await db.commit()
    await db.refresh(room)
    return room


async def bind_room_task(db: AsyncSession, room: Room, task_id: UUID) -> Room:
    room.task_id = task_id
    await db.commit()
    await db.refresh(room)
    return room


async def start_room_timer(db: AsyncSession, room: Room, duration_minutes: int = 90) -> Room:
    now = datetime.now(timezone.utc)
    locked_member_ids = await get_member_ids(db, room.id)
    room.timer_started_at = now
    room.timer_deadline_at = now + timedelta(minutes=duration_minutes)
    room.timer_stopped_at = None
    room.locked_member_ids = locked_member_ids
    await db.commit()
    await db.refresh(room)
    return room


async def reset_room_timer(db: AsyncSession, room: Room) -> Room:
    room.timer_started_at = None
    room.timer_deadline_at = None
    room.timer_stopped_at = None
    room.locked_member_ids = None
    await db.commit()
    await db.refresh(room)
    return room


async def stop_room_timer(db: AsyncSession, room: Room) -> Room:
    if not room.timer_started_at or not room.timer_deadline_at:
        return room

    if room.timer_stopped_at:
        return room

    room.timer_stopped_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(room)
    return room


async def delete_room(db: AsyncSession, room_id: UUID) -> None:
    await db.execute(delete(Message).where(Message.room_id == room_id))
    await db.execute(delete(RoomMember).where(RoomMember.room_id == room_id))
    await db.execute(delete(Room).where(Room.id == room_id))
    await db.commit()
