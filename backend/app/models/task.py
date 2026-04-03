import uuid

from sqlalchemy import Column, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy import ForeignKey

from app.db.session import Base


class Task(Base):
    __tablename__ = "tasks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(Text, nullable=False)
    requirements = Column(Text)
    scripts = Column(JSONB)
    discussion_template = Column(Text)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
