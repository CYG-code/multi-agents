"""create room_task_scripts table

Revision ID: f3a1b2c3d4e5
Revises: e9ad4c2b72a1
Create Date: 2026-05-07 12:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "f3a1b2c3d4e5"
down_revision: Union[str, None] = "e9ad4c2b72a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "room_task_scripts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("room_id", sa.UUID(), sa.ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("task_id", sa.UUID(), sa.ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True),
        sa.Column("scripts", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_room_task_scripts_room_id", "room_task_scripts", ["room_id"], unique=True)
    op.create_index("ix_room_task_scripts_task_id", "room_task_scripts", ["task_id"])


def downgrade() -> None:
    op.drop_index("ix_room_task_scripts_task_id")
    op.drop_index("ix_room_task_scripts_room_id")
    op.drop_table("room_task_scripts")
