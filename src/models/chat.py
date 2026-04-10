"""ChatMessage database model."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy import Column
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(UTC)


class ChatMessage(SQLModel, table=True):
    __tablename__ = "chat_messages"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    conversation_id: UUID = Field(
        sa_column=Column(
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    role: str  # "user" | "assistant"
    content: str
    intent: str | None = Field(default=None)
    created_at: datetime = Field(
        default_factory=_utcnow,
        sa_column=Column(TIMESTAMP(timezone=True), nullable=False),
    )
