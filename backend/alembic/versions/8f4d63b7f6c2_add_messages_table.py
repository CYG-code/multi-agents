"""add messages table

Revision ID: 8f4d63b7f6c2
Revises: 52a68928ab05
Create Date: 2026-04-06 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "8f4d63b7f6c2"
down_revision: Union[str, None] = "52a68928ab05"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


sender_type_enum = postgresql.ENUM("student", "agent", name="sendertype", create_type=False)
message_status_enum = postgresql.ENUM("streaming", "ok", "failed", name="messagestatus", create_type=False)


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            CREATE TYPE sendertype AS ENUM ('student', 'agent');
        EXCEPTION
            WHEN duplicate_object THEN NULL;
        END $$;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            CREATE TYPE messagestatus AS ENUM ('streaming', 'ok', 'failed');
        EXCEPTION
            WHEN duplicate_object THEN NULL;
        END $$;
        """
    )

    op.create_table(
        "messages",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("room_id", sa.UUID(), nullable=False),
        sa.Column("seq_num", sa.BigInteger(), nullable=False),
        sa.Column("sender_type", sender_type_enum, nullable=False),
        sa.Column("sender_id", sa.UUID(), nullable=True),
        sa.Column("agent_role", sa.String(length=50), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("status", message_status_enum, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["room_id"], ["rooms.id"]),
        sa.ForeignKeyConstraint(["sender_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("room_id", "seq_num", name="uq_messages_room_seq"),
    )
    op.create_index("idx_messages_room_seq", "messages", ["room_id", "seq_num"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_messages_room_seq", table_name="messages")
    op.drop_table("messages")
    op.execute("DROP TYPE IF EXISTS messagestatus")
    op.execute("DROP TYPE IF EXISTS sendertype")
