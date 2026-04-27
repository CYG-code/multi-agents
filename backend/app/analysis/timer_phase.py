from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models.room import Room


async def get_elapsed_seconds_from_timer_start(room_id: str) -> float | None:
    if isinstance(room_id, bytes):
        room_id = room_id.decode("utf-8", errors="ignore")

    try:
        parsed_room_id = UUID(str(room_id))
    except (ValueError, TypeError):
        return None

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Room.timer_started_at, Room.timer_stopped_at).where(Room.id == parsed_room_id)
        )
        row = result.first()

    if row is None:
        return None

    timer_started_at = row.timer_started_at
    timer_stopped_at = row.timer_stopped_at

    if timer_started_at is None:
        return None
    if timer_stopped_at is not None:
        # Timer already stopped after student submission; disable time-based triggers.
        return None

    if timer_started_at.tzinfo is None:
        timer_started_at = timer_started_at.replace(tzinfo=timezone.utc)

    now = datetime.now(timezone.utc)
    return max(0.0, (now - timer_started_at).total_seconds())
