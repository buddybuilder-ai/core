"""Chat API endpoints for RAG conversational AI."""

from typing import Any

from fastapi import APIRouter, Depends

from src.schemas.chat import ChatRequest, ChatResponse, SourceDocument

router = APIRouter(prefix="/chat", tags=["Chat"])


async def get_chat_service() -> Any:
    """Dependency injection stub for chat service.

    Will be replaced with actual service injection later.
    """
    return None


@router.post("/message", response_model=ChatResponse)
async def send_message(
    request: ChatRequest,
    service: Any = Depends(get_chat_service),
) -> ChatResponse:
    """Send a message to the chat AI.

    Args:
        request: Chat request with text and mode.
        service: Injected chat service (stub for now).

    Returns:
        ChatResponse with AI answer and source documents.
    """
    # Mock response - will be replaced with actual RAG implementation
    return ChatResponse(
        answer=f"Mock response for: {request.text} (mode: {request.mode.value})",
        source_documents=[
            SourceDocument(
                content="Mock source document from knowledge base",
                metadata={"page": 1, "source": "mock_doc.pdf"},
            )
        ],
    )
