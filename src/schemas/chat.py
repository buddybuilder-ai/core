"""Chat schemas for RAG conversational AI."""

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ChatMode(str, Enum):
    """Chat personality modes."""

    mentor = "mentor"
    buddy = "buddy"
    fun = "fun"


class SourceDocument(BaseModel):
    """Source document from RAG retrieval."""

    content: str = Field(..., description="Content of the source document")
    metadata: dict[str, Any] | None = Field(
        default=None, description="Document metadata"
    )


class ChatRequest(BaseModel):
    """Request schema for chat message."""

    text: str = Field(..., min_length=1, description="User message text")
    mode: ChatMode = Field(..., description="Chat personality mode")
    system_prompt: str | None = Field(
        default=None, description="Optional system prompt override"
    )


class ChatResponse(BaseModel):
    """Response schema for chat message."""

    answer: str = Field(..., description="AI-generated response")
    source_documents: list[SourceDocument] = Field(
        default_factory=list, description="Retrieved source documents"
    )
