import enum
import uuid

from sqlalchemy import BigInteger, Column, DateTime, Enum, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.db.session import Base


class SenderType(str, enum.Enum):
    student = "student"
    agent = "agent"


class MessageStatus(str, enum.Enum):
    streaming = "streaming"
    ok = "ok"
    failed = "failed"


class Message(Base):
    __tablename__ = "messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    room_id = Column(UUID(as_uuid=True), ForeignKey("rooms.id"), nullable=False)
    seq_num = Column(BigInteger, nullable=False)
    sender_type = Column(Enum(SenderType), nullable=False)
    sender_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    source_message_id = Column(UUID(as_uuid=True), ForeignKey("messages.id"), nullable=True)
    agent_role = Column(String(50), nullable=True)
    source_display_name_snapshot = Column(String(100), nullable=True)
    source_content_preview_snapshot = Column(Text, nullable=True)
    content = Column(Text, nullable=False)
    status = Column(Enum(MessageStatus), default=MessageStatus.ok, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("room_id", "seq_num", name="uq_messages_room_seq"),
        Index("idx_messages_room_seq", "room_id", "seq_num"),
        Index("idx_messages_source_message_id", "source_message_id"),
    )
