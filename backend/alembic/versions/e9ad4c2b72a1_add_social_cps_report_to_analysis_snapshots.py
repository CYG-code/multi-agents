"""add social_cps_report to analysis_snapshots

Revision ID: e9ad4c2b72a1
Revises: c4e5a97811ad
Create Date: 2026-04-28 14:45:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "e9ad4c2b72a1"
down_revision = "c4e5a97811ad"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "analysis_snapshots",
        sa.Column("social_cps_report", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("analysis_snapshots", "social_cps_report")

