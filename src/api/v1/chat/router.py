"""Chat API endpoints for RAG conversational AI."""

import json
import os
import subprocess
import uuid
from collections.abc import AsyncGenerator
from typing import Any

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
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
    """Dependency injection stub for chat service."""
    return None


@router.post("/message", response_model=ChatResponse)
async def send_message(
    request: ChatRequest,
    service: Any = Depends(get_chat_service),
) -> ChatResponse:
    """Send a message to the chat AI using LLM."""
    try:
        system_prompt = request.system_prompt or _get_default_system_prompt(request.mode.value)

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
                timeout=60.0,
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
                source_documents=[],
            )

    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="LLM request timed out")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Chat error: {str(e)}")


@router.post("/stream")
async def chat_stream(request: ChatStreamRequest) -> StreamingResponse:
    """Route user message and stream SSE events based on classified intent."""

    async def event_generator() -> AsyncGenerator[str, None]:
        from src.modules.layout.application.agent.personality import (
            detect_mode_switch,
            detect_mood,
        )

        mood = detect_mood(request.message)
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

        if result.intent == "set_mode":
            new_mode = result.extracted_params.get("mode") or detect_mode_switch(request.message) or "buddy"
            yield SSEEvent(
                event_type=SSEEventType.MODE_CHANGED,
                data={"mode": new_mode},
            ).to_sse()
            return

        elif result.intent == "new_layout":
            if not request.room_spec:
                yield SSEEvent(
                    event_type=SSEEventType.PIPELINE_FAILED,
                    data={"error": "room_spec is required for new_layout intent"},
                ).to_sse()
                return
            orchestrator = PipelineOrchestrator(PipelineConfig())
            async for event in orchestrator.run(request.room_spec, mode=request.mode):
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
            state = PipelineState(
                room_spec=request.room_spec or {},
                personality_mode=request.mode,
            )
            state.layout_items = request.current_layout
            async for event in ExplainerStep(PipelineConfig()).execute(state):
                yield event.to_sse()

        else:
            answer = await _answer_question(request.message, request.mode, mood)
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


async def _answer_question(message: str, mode: str, mood: str = "neutral") -> str:
    """Answer a feng shui / design question directly via LLM with RAG augmentation."""
    from src.modules.layout.application.agent.personality import get_system_prompt
    from src.modules.layout.application.services import ContextInjector

    system_prompt = get_system_prompt(mode, mood)
    rag_context = ""
    try:
        injector = ContextInjector()
        rag = await injector.retrieve({"room_type": "", "user_message": message})
        rag_context = rag.layout_prompt_context
    except Exception:
        pass

    augmented_message = f"{rag_context}\n\nUser question: {message}" if rag_context else message

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
                return str(response.json()["choices"][0]["message"]["content"])
            return f"LLM error {response.status_code}: {response.text}"
    except Exception as exc:
        return f"Failed to answer question: {exc}"


def _get_default_system_prompt(mode: str) -> str:
    """Get default system prompt based on chat mode."""
    prompts = {
        "mentor": (
            "You are a professional feng shui master and interior designer. Thai tone."
        ),
        "buddy": (
            "You are a friendly interior design assistant. Thai tone."
        ),
        "fun": (
            "You are an energetic, fun design buddy. Thai tone."
        ),
    }
    return prompts.get(mode, prompts["buddy"])


@router.post("/process-single-image")
async def process_single_image(
    image: UploadFile = File(...),
    target_height: str = Form("2.5")
):
    """API for processing a single image with AI to detect 3D objects."""
    # 1. ระบุพาธ Root ของโปรเจกต์
    base_dir = os.path.abspath(os.getcwd())
    assets_dir = os.path.join(base_dir, "assets")
    os.makedirs(assets_dir, exist_ok=True)

    # 2. บันทึกรูปภาพที่อัปโหลดมาลงใน assets
    file_id = uuid.uuid4().hex
    temp_image_path = os.path.join(assets_dir, f"{file_id}.jpg")
    with open(temp_image_path, "wb") as buffer:
        buffer.write(await image.read())

    # 3. สั่งรัน AI Script (detect_objects_2.py)
    try:

        print(f"🚀 AI Starting: height={target_height}m, image={temp_image_path}")

        # 4. อ่านไฟล์ JSON ที่ AI สร้างขึ้นใน assets
        json_path = os.path.join(assets_dir, "my_room_2_data.json")
        if os.path.exists(json_path):
            with open(json_path, encoding='utf-8') as f:
                return json.load(f)

        return {"status": "error", "message": "AI completed but JSON output was not found"}

    except subprocess.CalledProcessError as e:
        print(f"❌ AI Script Error (Stderr): {e.stderr}")
        return {"status": "error", "message": f"AI Error: {e.stderr}"}
    except Exception as e:
        print(f"❌ Server Exception: {str(e)}")
        return {"status": "error", "message": str(e)}
