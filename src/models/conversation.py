"""Conversation model."""
from datetime import UTC, datetime
from uuid import UUID, uuid4
from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Conversation(SQLModel, table=True):
    __tablename__ = "conversations"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="users.id", index=True)
    title: str = Field(default="New Conversation")
    kind: str = Field(default="general", index=True)
    created_at: datetime = Field(
        default_factory=_utcnow,
        sa_column=Column(TIMESTAMP(timezone=True), nullable=False),
    )
