"""add room agent mode

Revision ID: 9a2d1f7c4b11
Revises: f3a1b2c3d4e5
Create Date: 2026-05-08 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "9a2d1f7c4b11"
down_revision: Union[str, None] = "f3a1b2c3d4e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "rooms",
        sa.Column("agent_mode", sa.String(length=20), nullable=False, server_default="multi"),
    )
    op.create_check_constraint(
        "ck_rooms_agent_mode_valid",
        "rooms",
        "agent_mode IN ('none', 'single', 'multi')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_rooms_agent_mode_valid", "rooms", type_="check")
    op.drop_column("rooms", "agent_mode")
