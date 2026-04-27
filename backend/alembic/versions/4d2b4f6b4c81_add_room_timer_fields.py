"""add room timer fields

Revision ID: 4d2b4f6b4c81
Revises: c13f9a6a4d21
Create Date: 2026-04-27 23:55:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "4d2b4f6b4c81"
down_revision: Union[str, None] = "c13f9a6a4d21"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("rooms", sa.Column("timer_started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("rooms", sa.Column("timer_deadline_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("rooms", "timer_deadline_at")
    op.drop_column("rooms", "timer_started_at")
