"""Chat API endpoints for RAG conversational AI."""

import httpx
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from src.config.settings import get_settings
from src.modules.layout.application.modifier import ModifierAgent
from src.modules.layout.application.pipeline import PipelineConfig, PipelineOrchestrator
from src.modules.layout.application.pipeline.models import (
    PipelineState,
    SSEEvent,
    SSEEventType,
)
from src.modules.layout.application.pipeline.steps import ExplainerStep
from src.modules.layout.infrastructure.llm.router_agent import RouterAgent
from src.schemas.chat import ChatRequest, ChatResponse
from src.schemas.chat_stream import ChatStreamRequest

router = APIRouter(prefix="/chat", tags=["Chat"])
settings = get_settings()


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
    """Send a message to the chat AI using LLM.

    Args:
        request: Chat request with text and mode.
        service: Injected chat service (stub for now).

    Returns:
        ChatResponse with AI answer and source documents.
    """
    try:
        # Use system prompt if provided, otherwise use mode-based default
        system_prompt = request.system_prompt or _get_default_system_prompt(
            request.mode.value
        )

        # Call OpenRouter API with extended timeout for free models
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{settings.OPENROUTER_BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://buddybuilder.ai",
                    "X-Title": "BuddyBuilder AI",
                },
                json={
                    "model": settings.LLM_MODEL_RAG,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": request.text},
                    ],
                    "temperature": settings.LLM_TEMPERATURE_RAG,
                    "max_tokens": 1000,
                },
                timeout=60.0,  # Increased to 60s for free models
            )

            if response.status_code != 200:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"LLM API error: {response.text}",
                )

            data = response.json()
            answer = data["choices"][0]["message"]["content"]

            return ChatResponse(
                answer=answer,
                source_documents=[],  # RAG implementation coming later
            )

    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="LLM request timed out")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Chat error: {str(e)}")


@router.post("/stream")
async def chat_stream(request: ChatStreamRequest) -> StreamingResponse:
    """Route user message and stream SSE events based on classified intent.

    The router agent classifies the message into one of:
    - new_layout: triggers the full 5-step pipeline
    - modify:     triggers ModifierAgent for incremental layout changes
    - explain:    runs ExplainerStep on the current layout
    - question:   answers directly via LLM (no layout generation)

    All paths stream SSE events in the same format as /layout/generate/stream.

    Args:
        request: ChatStreamRequest with message, layout context, and room spec.

    Returns:
        SSE stream of events.
    """
    async def event_generator():
        # --- 1. Classify intent ---
        router_agent = RouterAgent()
        result = await router_agent.classify(
            message=request.message,
            has_existing_layout=bool(request.current_layout),
            conversation_history=request.conversation_history[-4:],
        )

        yield SSEEvent(
            event_type=SSEEventType.ROUTER_CLASSIFIED,
            data={
                "intent": result.intent,
                "confidence": result.confidence,
                "extracted_params": result.extracted_params,
            },
        ).to_sse()

        # --- 2. Dispatch to handler ---
        if result.intent == "new_layout":
            if not request.room_spec:
                yield SSEEvent(
                    event_type=SSEEventType.PIPELINE_FAILED,
                    data={"error": "room_spec is required for new_layout intent"},
                ).to_sse()
                return
            orchestrator = PipelineOrchestrator(PipelineConfig())
            async for event in orchestrator.run(request.room_spec):
                yield event.to_sse()

        elif result.intent == "modify":
            if not request.current_layout or not request.room_spec:
                yield SSEEvent(
                    event_type=SSEEventType.PIPELINE_FAILED,
                    data={"error": "current_layout and room_spec are required for modify intent"},
                ).to_sse()
                return
            modifier = ModifierAgent()
            async for event in modifier.apply(
                current_layout=request.current_layout,
                room_spec=request.room_spec,
                modification_request=request.message,
                extracted_params=result.extracted_params,
            ):
                yield event.to_sse()

        elif result.intent == "explain":
            state = PipelineState(room_spec=request.room_spec or {})
            state.layout_items = request.current_layout
            async for event in ExplainerStep(PipelineConfig()).execute(state):
                yield event.to_sse()

        else:  # "question" (also the fallback)
            answer = await _answer_question(request.message, request.mode)
            yield SSEEvent(
                event_type=SSEEventType.PIPELINE_COMPLETED,
                data={"intent": "question", "answer": answer},
            ).to_sse()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


async def _answer_question(message: str, mode: str) -> str:
    """Answer a feng shui / design question directly via LLM with RAG augmentation.

    Retrieves relevant feng shui rules from the knowledge base and prepends them
    to the user message for context-aware answers.  Falls back to plain LLM if
    RAG retrieval fails or returns no results.

    Reuses the same OpenRouter call logic as send_message().
    Returns the answer string, or an error message if the call fails.
    """
    from src.modules.layout.application.services import ContextInjector

    system_prompt = _get_default_system_prompt(mode)

    # RAG augmentation — graceful; never raises
    rag_context = ""
    try:
        injector = ContextInjector()
        rag = await injector.retrieve({"room_type": "", "user_message": message})
        rag_context = rag.layout_prompt_context
    except Exception:
        pass

    augmented_message = (
        f"{rag_context}\n\nUser question: {message}" if rag_context else message
    )

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{settings.OPENROUTER_BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://buddybuilder.ai",
                    "X-Title": "BuddyBuilder AI",
                },
                json={
                    "model": settings.LLM_MODEL_RAG,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": augmented_message},
                    ],
                    "temperature": settings.LLM_TEMPERATURE_RAG,
                    "max_tokens": 1000,
                },
                timeout=60.0,
            )
            if response.status_code == 200:
                return response.json()["choices"][0]["message"]["content"]
            return f"LLM error {response.status_code}: {response.text}"
    except Exception as exc:
        return f"Failed to answer question: {exc}"


def _get_default_system_prompt(mode: str) -> str:
    """Get default system prompt based on chat mode."""
    prompts = {
        "mentor": (
            "You are a professional feng shui master and interior designer. "
            "Provide detailed, educational explanations with formal tone in Thai. "
            "Be knowledgeable and thorough."
        ),
        "buddy": (
            "You are a friendly interior design assistant. "
            "Use casual, warm tone in Thai. Be conversational and approachable."
        ),
        "fun": (
            "You are an energetic, fun design buddy. "
            "Use playful, exciting tone in Thai. Be entertaining while informative."
        ),
    }
    return prompts.get(mode, prompts["buddy"])
