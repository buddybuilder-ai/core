"""add_conversation_kind

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-18 00:00:00.000000
"""
import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column("kind", sa.String(), nullable=False, server_default="general"),
    )
    op.create_index("ix_conversations_kind", "conversations", ["kind"])

    # Backfill: conversations already linked to a project → mark as "project"
    op.execute(
        """
        UPDATE conversations
        SET kind = 'project'
        WHERE id IN (
            SELECT conversation_id FROM projects WHERE conversation_id IS NOT NULL
        )
        """
    )


def downgrade() -> None:
    op.drop_index("ix_conversations_kind", table_name="conversations")
    op.drop_column("conversations", "kind")
