"""add room timer stopped_at field

Revision ID: 7f31a2d9b6e4
Revises: 4d2b4f6b4c81
Create Date: 2026-04-28 00:40:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "7f31a2d9b6e4"
down_revision: Union[str, None] = "4d2b4f6b4c81"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("rooms", sa.Column("timer_stopped_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("rooms", "timer_stopped_at")
