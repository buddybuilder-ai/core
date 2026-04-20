"""Project database model."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Column, Text
from sqlalchemy.dialects.postgresql import JSON, TIMESTAMP
from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Project(SQLModel, table=True):
    __tablename__ = "projects"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="users.id", index=True)
    conversation_id: UUID | None = Field(default=None, foreign_key="conversations.id", index=True)
    name: str
    room_spec: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    latest_layout: list[dict[str, Any]] | None = Field(
        default=None, sa_column=Column(JSON, nullable=True)
    )
    # Base64-encoded PNG data URL captured from the editor's 3D canvas.
    # Stored inline to keep deployment dependency surface small; swap to
    # object storage if the payload size becomes a concern.
    preview_image: str | None = Field(
        default=None, sa_column=Column(Text, nullable=True)
    )
    is_active: bool = Field(default=True)
    created_at: datetime = Field(
        default_factory=_utcnow,
        sa_column=Column(TIMESTAMP(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=_utcnow,
        sa_column=Column(TIMESTAMP(timezone=True), nullable=False),
    )
