"""Schemas for the /chat/stream endpoint."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ChatStreamRequest(BaseModel):
    """Request schema for the chat/stream SSE endpoint.

    Attributes:
        message: The user's message.
        mode: Chat personality mode (buddy|mentor|fun).
        current_layout: Existing layout items from a previous pipeline run.
            Empty list means no existing layout.
        room_spec: Room specification dict (required for new_layout intent).
        conversation_history: Recent conversation turns for context.
            Each entry: {"role": "user"|"assistant", "content": "..."}
    """

    message: str = Field(..., min_length=1, description="User message")
    mode: str = Field(default="buddy", description="Chat personality mode")
    current_layout: list[dict[str, Any]] = Field(
        default_factory=list, description="Existing layout items"
    )
    room_spec: dict[str, Any] | None = Field(
        default=None, description="Room specification (required for new_layout)"
    )
    conversation_history: list[dict[str, str]] = Field(
        default_factory=list, description="Recent conversation history"
    )
    clarification_answers: dict[str, str] = Field(
        default_factory=dict,
        description="Answers to clarification questions keyed by question_id",
    )
