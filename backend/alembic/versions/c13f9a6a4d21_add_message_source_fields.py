"""add message source linkage fields

Revision ID: c13f9a6a4d21
Revises: 8f4d63b7f6c2
Create Date: 2026-04-27 21:20:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c13f9a6a4d21"
down_revision: Union[str, None] = "8f4d63b7f6c2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("messages", sa.Column("source_message_id", sa.UUID(), nullable=True))
    op.add_column("messages", sa.Column("source_display_name_snapshot", sa.String(length=100), nullable=True))
    op.add_column("messages", sa.Column("source_content_preview_snapshot", sa.Text(), nullable=True))
    op.create_foreign_key(
        "fk_messages_source_message_id",
        "messages",
        "messages",
        ["source_message_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("idx_messages_source_message_id", "messages", ["source_message_id"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_messages_source_message_id", table_name="messages")
    op.drop_constraint("fk_messages_source_message_id", "messages", type_="foreignkey")
    op.drop_column("messages", "source_content_preview_snapshot")
    op.drop_column("messages", "source_display_name_snapshot")
    op.drop_column("messages", "source_message_id")

