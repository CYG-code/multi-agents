import uuid
import enum

from sqlalchemy import Column, String, Enum, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.db.session import Base


class RoomStatus(str, enum.Enum):
    waiting = "waiting"
    active = "active"
    ended = "ended"


class Room(Base):
    __tablename__ = "rooms"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(200), nullable=False)
    task_id = Column(UUID(as_uuid=True), ForeignKey("tasks.id"), nullable=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    status = Column(Enum(RoomStatus), default=RoomStatus.waiting, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    ended_at = Column(DateTime(timezone=True), nullable=True)
    timer_started_at = Column(DateTime(timezone=True), nullable=True)
    timer_deadline_at = Column(DateTime(timezone=True), nullable=True)
