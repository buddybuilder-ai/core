"""Project and chat message request/response schemas."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class ProjectCreate(BaseModel):
    name: str
    room_spec: dict[str, Any]


class ProjectUpdate(BaseModel):
    name: str | None = None
    room_spec: dict[str, Any] | None = None
    latest_layout: list[dict[str, Any]] | None = None
    preview_image: str | None = None


class ProjectResponse(BaseModel):
    id: UUID
    name: str
    room_spec: dict[str, Any]
    latest_layout: list[dict[str, Any]] | None
    preview_image: str | None
    conversation_id: UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ChatMessageCreate(BaseModel):
    role: str  # "user" | "assistant"
    content: str
    intent: str | None = None


class ChatMessageResponse(BaseModel):
    id: UUID
    role: str
    content: str
    intent: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
