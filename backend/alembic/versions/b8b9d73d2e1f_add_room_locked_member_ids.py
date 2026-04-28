"""add room locked_member_ids field

Revision ID: b8b9d73d2e1f
Revises: 7f31a2d9b6e4
Create Date: 2026-04-28 13:25:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "b8b9d73d2e1f"
down_revision = "7f31a2d9b6e4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("rooms", sa.Column("locked_member_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    op.drop_column("rooms", "locked_member_ids")

