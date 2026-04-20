"""Chat API endpoints for RAG conversational AI."""

import json
import os
import subprocess
import uuid
from collections.abc import AsyncGenerator
from typing import Any, cast

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

        # --- 1a. Empty-room guard ---
        # If the user asks to arrange/rearrange a room that has no furniture,
        # don't run the pipeline (it produces random guesses). Tell the user
        # to add furniture first.
        if result.intent in {"new_layout", "rearrange_all", "modify"} and not request.current_layout:
            yield SSEEvent(
                event_type=SSEEventType.ANSWER,
                data={
                    "answer": (
                        "ห้องยังว่างอยู่เลยครับ ลองเพิ่มเฟอร์นิเจอร์ที่อยากใช้เข้าไปในห้องก่อน "
                        "(เช่น เตียง โซฟา โต๊ะ ตู้) แล้วค่อยบอกผมให้จัดวางใหม่ให้ถูกหลักฮวงจุ้ยนะครับ"
                    )
                },
            ).to_sse()
            return

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

            RECOMMENDED questions that the user did not answer fall back to
            their predefined default_value so the LLM always receives a full
            set of hints (pipeline never loops asking the same things).
            """
            from src.modules.layout.infrastructure.tools.user_clarifier_tool import (
                QuestionPriority,
                UserClarifierTool,
            )

            spec = dict(room_spec)
            merged: dict[str, str] = {}
            for q in UserClarifierTool().get_questions_for_room_type("studio_apartment"):
                if q.priority == QuestionPriority.RECOMMENDED and q.default_value is not None:
                    merged[q.id] = q.default_value
            merged.update(answers or {})
            answers = merged

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
            new_mode = (
                result.extracted_params.get("mode")
                or detect_mode_switch(request.message)
                or "buddy"
            )
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
            if not request.room_spec:
                yield SSEEvent(
                    event_type=SSEEventType.PIPELINE_FAILED,
                    data={"error": "current_layout and room_spec are required for rearrange_all intent"},
                ).to_sse()
                return
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

        else:
            answer = await _answer_question(request.message, request.mode, mood)
            yield SSEEvent(
                event_type=SSEEventType.ANSWER,
                data={"answer": answer},
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


@router.post("/rag")
async def chat_rag_only(request: ChatStreamRequest) -> StreamingResponse:
    """RAG-only chat endpoint — ตอบคำถามฮวงจุ้ยโดยตรง ไม่ผ่าน router agent และไม่สร้าง layout.

    ใช้สำหรับหน้า Chatbot โดยเฉพาะ.
    """

    async def event_generator() -> AsyncGenerator[str, None]:
        from src.modules.layout.application.services.rag_service import FengShuiRAGService

        service = FengShuiRAGService()
        full_answer = ""
        try:
            async for kind, text, _sources in service.ask_stream(
                question=request.message,
                mode=request.mode,
                conversation_history=request.conversation_history or [],
            ):
                if kind == "delta":
                    yield SSEEvent(
                        event_type=SSEEventType.ANSWER_DELTA,
                        data={"delta": text},
                    ).to_sse()
                elif kind == "final":
                    full_answer = text
        except Exception as exc:  # pragma: no cover - safety net
            full_answer = full_answer or f"ขออภัยครับ เกิดข้อผิดพลาด: {exc}"

        # Keep the `answer` event as the terminal marker so legacy clients that
        # only listen for ANSWER still receive the full text.
        yield SSEEvent(
            event_type=SSEEventType.ANSWER,
            data={"answer": full_answer},
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
        "mentor": ("You are a professional feng shui master and interior designer. Thai tone."),
        "buddy": ("You are a friendly interior design assistant. Thai tone."),
        "fun": ("You are an energetic, fun design buddy. Thai tone."),
    }
    return prompts.get(mode, prompts["buddy"])


@router.post("/process-single-image")
async def process_single_image(
    image: UploadFile = File(...), target_height: str = Form("2.5")
) -> dict[str, Any]:
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
            with open(json_path, encoding="utf-8") as f:
                return cast(dict[str, Any], json.load(f))

        return {"status": "error", "message": "AI completed but JSON output was not found"}

    except subprocess.CalledProcessError as e:
        print(f"❌ AI Script Error (Stderr): {e.stderr}")
        return {"status": "error", "message": f"AI Error: {e.stderr}"}
    except Exception as e:
        print(f"❌ Server Exception: {str(e)}")
        return {"status": "error", "message": str(e)}
