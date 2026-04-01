"""Chat API endpoints for RAG conversational AI."""

import os
import uuid
import json
import subprocess
from collections.abc import AsyncGenerator
from typing import Any

import asyncio
import anyio

import httpx
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse

from src.config.settings import get_settings
from src.modules.layout.application.modifier import ModifierAgent
from src.modules.layout.application.modifier.rearrange_agent import RearrangeAgent
from src.modules.layout.application.pipeline import PipelineConfig, PipelineOrchestrator
from src.modules.layout.application.pipeline.models import (
    PipelineState,
    SSEEvent,
    SSEEventType,
)
from src.modules.layout.application.pipeline.steps import ExplainerStep
from src.modules.layout.application.services.clarification_gate import get_pending_questions
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
        from src.modules.layout.application.services.rag_service import FengShuiRAGService
        from src.schemas.chat import SourceDocument

        service = FengShuiRAGService()
        answer, source_docs = await service.ask(
            question=request.text,
            mode=request.mode.value,
            conversation_history=[],
        )

        return ChatResponse(
            answer=answer,
            source_documents=[
                SourceDocument(
                    content=d["content"],
                    metadata=d.get("metadata"),
                )
                for d in source_docs
            ],
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

        # --- 1b. Clarification gate (stateless — skipped when answers present) ---
        pending_questions = get_pending_questions(
            intent=result.intent,
            clarification_answers=request.clarification_answers,
            has_existing_layout=bool(request.current_layout),
        )
        if pending_questions:
            yield SSEEvent(
                event_type=SSEEventType.CLARIFICATION_NEEDED,
                data={
                    "questions": pending_questions,
                    "original_message": request.message,
                },
            ).to_sse()
            return

        # --- 2. Merge clarification answers into room_spec ---
        _OPPOSITE_WALL: dict[str, str] = {
            "south": "north",
            "north": "south",
            "east": "west",
            "west": "east",
        }
        _SIDE_WALLS: dict[str, tuple[str, str]] = {
            "south": ("west", "east"),
            "north": ("west", "east"),
            "east": ("south", "north"),
            "west": ("south", "north"),
        }

        def _apply_clarification_answers(
            room_spec: dict[str, Any], answers: dict[str, str]
        ) -> dict[str, Any]:
            """Inject clarification answers into room_spec.

            Converts answers to explicit placement_hint strings that the LLM
            reads as hard constraints, e.g.:
              "โซนนอนควรอยู่ส่วนไหน → ตรงข้ามประตู"
              → placement_hint: "sofa_bed/bed: target_wall=north (opposite of south door)"
            """
            if not answers:
                return room_spec
            spec = dict(room_spec)

            # Budget level → top-level field
            budget_map = {"ประหยัด": "low", "กลาง": "medium", "สูง": "high"}
            if "budget_level" in answers:
                spec["budget_level"] = budget_map.get(answers["budget_level"], "medium")

            # Build placement hints from answers
            prefs = dict(spec.get("user_preferences") or {})
            hints: list[str] = []

            # Determine door wall for relative directions
            doors = spec.get("doors") or []
            door_wall = str(doors[0].get("wall", "south")).lower() if doors else "south"
            opp = _OPPOSITE_WALL.get(door_wall, "north")
            sides = _SIDE_WALLS.get(door_wall, ("west", "east"))

            sleep_ans = answers.get("sleep_zone_preference", "")
            if "ตรงข้ามประตู" in sleep_ans or "ผู้บัญชาการ" in sleep_ans:
                hints.append(
                    f"SLEEP ZONE: sofa_bed / bed MUST use target_wall={opp} "
                    f"(wall opposite the {door_wall} door — command position)"
                )
            elif "ซ้าย" in sleep_ans:
                hints.append(
                    f"SLEEP ZONE: sofa_bed / bed MUST use target_wall={sides[0]} "
                    f"(left wall as seen from door)"
                )
            elif "ขวา" in sleep_ans:
                hints.append(
                    f"SLEEP ZONE: sofa_bed / bed MUST use target_wall={sides[1]} "
                    f"(right wall as seen from door)"
                )

            sofa_ans = answers.get("sofa_bed_or_separate", "")
            if "โซฟาเตียง" in sofa_ans:
                hints.append(
                    "FURNITURE TYPE: use sofa_bed (id=sofa_bed_001 or sofa_bed_002) "
                    "as the primary sleep+seating piece — do NOT place a separate bed AND sofa"
                )
            elif "เตียงแยก" in sofa_ans:
                hints.append(
                    "FURNITURE TYPE: use a separate bed (id=bed_single_001 or bed_queen_001) "
                    "AND a sofa — two distinct pieces"
                )
            elif "เตียงเดี่ยว" in sofa_ans:
                hints.append(
                    "FURNITURE TYPE: use a single bed only (id=bed_single_001) — no sofa needed"
                )

            work_ans = answers.get("work_area_needed", "")
            if work_ans.lower() in ("yes", "ใช่"):
                hints.append(
                    "WORK ZONE: include a folding_desk (id=folding_desk_001 or folding_desk_002) "
                    f"on the {sides[0]} or {sides[1]} wall (NOT on the sleep wall)"
                )
            elif work_ans.lower() in ("no", "ไม่ใช่"):
                hints.append("WORK ZONE: no desk needed — omit folding_desk from layout")

            if hints:
                prefs["placement_constraints"] = "\n".join(hints)

            prefs["clarification_answers"] = answers
            spec["user_preferences"] = prefs
            return spec

        # --- 3. Dispatch to handler ---
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
            room_spec = _apply_clarification_answers(
                dict(request.room_spec), request.clarification_answers
            )
            prefs = dict(room_spec.get("user_preferences") or {})
            prefs["user_message"] = request.message
            room_spec["user_preferences"] = prefs
            orchestrator = PipelineOrchestrator(PipelineConfig())
            async for event in orchestrator.run(room_spec, mode=request.mode):
                yield event.to_sse()

        elif result.intent == "modify":
            # If no existing layout, downgrade to new_layout and inject placement preference
            if not request.current_layout:
                if not request.room_spec:
                    yield SSEEvent(
                        event_type=SSEEventType.PIPELINE_FAILED,
                        data={"error": "room_spec is required"},
                    ).to_sse()
                    return
                room_spec = _apply_clarification_answers(
                    dict(request.room_spec), request.clarification_answers
                )
                prefs = dict(room_spec.get("user_preferences") or {})
                prefs["user_message"] = request.message
                params = result.extracted_params
                if params.get("target_furniture") and params.get("details"):
                    prefs["placement_hint"] = f"{params['target_furniture']}: {params['details']}"
                room_spec["user_preferences"] = prefs
                orchestrator = PipelineOrchestrator(PipelineConfig())
                async for event in orchestrator.run(room_spec, mode=request.mode):
                    yield event.to_sse()
                return
            if not request.room_spec:
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

        elif result.intent == "rearrange_all":
            if not request.current_layout or not request.room_spec:
                # No existing layout — fall through to new_layout pipeline
                if not request.room_spec:
                    yield SSEEvent(
                        event_type=SSEEventType.PIPELINE_FAILED,
                        data={"error": "room_spec is required"},
                    ).to_sse()
                    return
                room_spec = _apply_clarification_answers(
                    dict(request.room_spec), request.clarification_answers
                )
                prefs = dict(room_spec.get("user_preferences") or {})
                prefs["user_message"] = request.message
                room_spec["user_preferences"] = prefs
                orchestrator = PipelineOrchestrator(PipelineConfig())
                async for event in orchestrator.run(room_spec, mode=request.mode):
                    yield event.to_sse()
            else:
                rearrange_room_spec = _apply_clarification_answers(
                    dict(request.room_spec), request.clarification_answers
                )
                rearrange_prefs = dict(rearrange_room_spec.get("user_preferences") or {})
                rearrange_prefs["user_message"] = request.message
                rearrange_room_spec["user_preferences"] = rearrange_prefs
                agent = RearrangeAgent()
                async for event in agent.apply(
                    current_layout=request.current_layout,
                    room_spec=rearrange_room_spec,
                    modification_request=request.message,
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

        else:  # "question" (also the fallback)
            answer = await _answer_question(
                request.message,
                request.mode,
                mood,
                request.conversation_history,
            )
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


async def _answer_question(
    message: str,
    mode: str,
    mood: str = "neutral",
    conversation_history: list[dict[str, str]] | None = None,
) -> str:
    """Answer a feng shui / design question using FengShuiRAGService.

    Implements the full feng-shui-rag ConversationRAGChain flow:
    - 2-layer relevance check (domain keywords + ChromaDB L2 distance)
    - MMR retrieval from feng-shui-rag vectorstore
    - Thai-enforced system prompt with mode personality
    - Conversation history injected into prompt

    Falls back gracefully if vectorstore is unavailable.
    Returns the answer string.
    """
    from src.modules.layout.application.services.rag_service import FengShuiRAGService

    service = FengShuiRAGService()
    answer, _ = await service.ask(
        question=message,
        mode=mode,
        conversation_history=conversation_history or [],
    )
    return answer


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
    base_dir = os.path.abspath(os.getcwd())
    assets_dir = os.path.join(base_dir, "assets")
    os.makedirs(assets_dir, exist_ok=True)
    
    # 1. บันทึกรูปภาพด้วย ID ที่ไม่ซ้ำ
    file_id = uuid.uuid4().hex
    temp_image_path = os.path.join(assets_dir, f"{file_id}.jpg")
    
    async with anyio.open_file(temp_image_path, "wb") as buffer:
        await buffer.write(await image.read())

    # 2. รัน AI Script แบบ Non-blocking
    try:
        script_path = os.path.join(base_dir, "src", "detect_objects_2.py")
        print(f"🚀 AI Starting: ID={file_id}, height={target_height}m")

        # ใช้ asyncio เพื่อไม่ให้ Server ค้าง
        process = await asyncio.create_subprocess_exec(
            "python", script_path, target_height, temp_image_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=base_dir
        )

        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            error_msg = stderr.decode('utf-8', errors='ignore')
            print(f"❌ AI Script Error: {error_msg}")
            return {"status": "error", "message": f"AI Error: {error_msg}"}

        # 3. อ่านไฟล์ JSON (ในกรณีที่ AI เขียนลงไฟล์กลาง ให้ระวังเรื่องการอ่าน)
        # แนะนำให้แก้ Script AI ให้รับ Argument พาธสำหรับ Output JSON ด้วย
        json_path = os.path.join(assets_dir, "my_room_2_data.json")
        
        if os.path.exists(json_path):
            async with anyio.open_file(json_path, 'r', encoding='utf-8') as f:
                content = await f.read()
                return json.loads(content)
        
        return {"status": "error", "message": "AI completed but JSON output was not found"}

    except Exception as e:
        print(f"❌ Server Exception: {str(e)}")
        return {"status": "error", "message": str(e)}