"""add analysis_snapshots table

Revision ID: c4e5a97811ad
Revises: b8b9d73d2e1f
Create Date: 2026-04-28 14:10:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "c4e5a97811ad"
down_revision = "b8b9d73d2e1f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "analysis_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("room_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("analyzed_message_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("analysis_context", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("rule_metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("cognitive_report", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("behavioral_report", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("emotional_report", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("social_report", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("interaction_report", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("diversity_score", sa.Float(), nullable=True),
        sa.Column("progress_score", sa.Float(), nullable=True),
        sa.Column("behavioral_score", sa.Float(), nullable=True),
        sa.Column("social_score", sa.Float(), nullable=True),
        sa.Column("balance_score", sa.Float(), nullable=True),
        sa.Column("participation_scores", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("is_single_dominated", sa.Boolean(), nullable=True),
        sa.Column("dominant_members", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("silent_members", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("emotion_flags", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("should_intervene", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("selected_agent_role", sa.String(length=50), nullable=True),
        sa.Column("selected_strategy", sa.Text(), nullable=True),
        sa.Column("dispatcher_decision", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["room_id"], ["rooms.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_analysis_snapshots_room_created", "analysis_snapshots", ["room_id", "created_at"])


def downgrade() -> None:
    op.drop_index("idx_analysis_snapshots_room_created", table_name="analysis_snapshots")
    op.drop_table("analysis_snapshots")

