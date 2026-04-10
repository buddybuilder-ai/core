"""add_conversations

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-11 00:00:00.000000
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create conversations table
    op.create_table(
        "conversations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("title", sa.String(), nullable=False, server_default="New Conversation"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_conversations_user_id", "conversations", ["user_id"])

    # Add conversation_id to projects
    op.add_column("projects", sa.Column("conversation_id", UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_projects_conversation_id", "projects", "conversations",
        ["conversation_id"], ["id"], ondelete="SET NULL"
    )
    op.create_index("ix_projects_conversation_id", "projects", ["conversation_id"])

    # Drop old chat_messages (project_id based) and recreate with conversation_id
    op.drop_index("ix_chat_messages_project_id", table_name="chat_messages")
    op.drop_table("chat_messages")
    op.create_table(
        "chat_messages",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "conversation_id", UUID(as_uuid=True),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("content", sa.String(), nullable=False),
        sa.Column("intent", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_chat_messages_conversation_id", "chat_messages", ["conversation_id"])


def downgrade() -> None:
    op.drop_index("ix_chat_messages_conversation_id", table_name="chat_messages")
    op.drop_table("chat_messages")
    op.create_table(
        "chat_messages",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "project_id", UUID(as_uuid=True),
            sa.ForeignKey("projects.id"), nullable=False
        ),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("content", sa.String(), nullable=False),
        sa.Column("intent", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_chat_messages_project_id", "chat_messages", ["project_id"])
    op.drop_constraint("fk_projects_conversation_id", "projects", type_="foreignkey")
    op.drop_index("ix_projects_conversation_id", table_name="projects")
    op.drop_column("projects", "conversation_id")
    op.drop_index("ix_conversations_user_id", table_name="conversations")
    op.drop_table("conversations")
