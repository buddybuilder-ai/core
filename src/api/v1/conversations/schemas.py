"""Conversation schemas."""
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel


class ConversationCreate(BaseModel):
    title: str = "New Conversation"


class ConversationResponse(BaseModel):
    id: UUID
    user_id: UUID
    title: str
    kind: str
    created_at: datetime
    model_config = {"from_attributes": True}


class ChatMessageCreate(BaseModel):
    role: str
    content: str
    intent: str | None = None


class ChatMessageResponse(BaseModel):
    id: UUID
    conversation_id: UUID
    role: str
    content: str
    intent: str | None
    created_at: datetime
    model_config = {"from_attributes": True}
