from __future__ import annotations

import uuid

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.db.session import Base


class AnalysisSnapshot(Base):
    __tablename__ = "analysis_snapshots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    room_id = Column(UUID(as_uuid=True), ForeignKey("rooms.id"), nullable=False, index=True)

    analyzed_message_count = Column(Integer, nullable=False, default=0)
    analysis_context = Column(JSONB, nullable=True)
    rule_metrics = Column(JSONB, nullable=True)

    cognitive_report = Column(JSONB, nullable=True)
    behavioral_report = Column(JSONB, nullable=True)
    emotional_report = Column(JSONB, nullable=True)
    social_report = Column(JSONB, nullable=True)
    social_cps_report = Column(JSONB, nullable=True)
    interaction_report = Column(JSONB, nullable=True)  # backward compatibility

    diversity_score = Column(Float, nullable=True)
    progress_score = Column(Float, nullable=True)
    behavioral_score = Column(Float, nullable=True)
    social_score = Column(Float, nullable=True)
    balance_score = Column(Float, nullable=True)
    participation_scores = Column(JSONB, nullable=True)
    is_single_dominated = Column(Boolean, nullable=True)
    dominant_members = Column(JSONB, nullable=True)
    silent_members = Column(JSONB, nullable=True)
    emotion_flags = Column(JSONB, nullable=True)

    should_intervene = Column(Boolean, nullable=False, default=False)
    selected_agent_role = Column(String(50), nullable=True)
    selected_strategy = Column(Text, nullable=True)
    dispatcher_decision = Column(JSONB, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("idx_analysis_snapshots_room_created", "room_id", "created_at"),
    )
