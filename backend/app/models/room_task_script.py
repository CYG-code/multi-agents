from __future__ import annotations

import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Index, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.db.session import Base


class RoomTaskScript(Base):
    """
    Room-scoped task script state.

    Each room has at most one row. The `scripts` JSONB column stores the
    same shape as Task.scripts (current_status, next_goal, history,
    pending_proposal), but is isolated per room so multiple rooms
    sharing the same task_id do not crosstalk.
    """

    __tablename__ = "room_task_scripts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    room_id = Column(
        UUID(as_uuid=True),
        ForeignKey("rooms.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    task_id = Column(
        UUID(as_uuid=True),
        ForeignKey("tasks.id", ondelete="SET NULL"),
        nullable=True,
    )
    scripts = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_room_task_scripts_room_id", "room_id", unique=True),
        Index("ix_room_task_scripts_task_id", "task_id"),
    )
