"""Layout API endpoints.

Primary endpoints:
    GET  /layout/health            — health check
    POST /layout/generate/stream   — 5-step agentic pipeline with SSE streaming

Deprecated / removed:
    POST /layout/generate          — removed (was a static mock; use /generate/stream)
    POST /layout/feng-shui         — removed (was LayoutOrchestrator; use /generate/stream)
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from src.schemas.layout import FengShuiLayoutRequest

router = APIRouter(prefix="/layout", tags=["Layout"])


@router.post("/generate/stream")
async def generate_layout_stream(
    request: FengShuiLayoutRequest,
    max_repair_loops: int = 3,
    mode: str = "buddy",
) -> StreamingResponse:
    """Generate a feng shui layout with SSE streaming.

    Streams real-time progress events as the 5-step agentic pipeline
    processes the layout:
        1. Structured Data Builder
        2. Layout Generator (Planner)
        3. Rule Checker (Dual-rule)
        4. Repair (Auto-fix) — loops with Step 3 if conflicts exist
        5. Explainer — Thai natural-language explanation styled to ``mode``

    Args:
        request: Feng shui layout request.
        max_repair_loops: Max repair iterations (default 3).
        mode: Personality mode for the Explainer step ("buddy"|"mentor"|"fun").

    Returns:
        SSE stream of pipeline events.
    """
    from src.modules.layout.application.pipeline import PipelineConfig, PipelineOrchestrator
    config = PipelineConfig(max_repair_loops=max_repair_loops)
    orchestrator = PipelineOrchestrator(config)

    room_spec = {
        "room_type": request.room_type.value,
        "dimensions": {
            "width": request.dimensions.width,
            "depth": request.dimensions.depth,
        },
        "width": request.dimensions.width,
        "depth": request.dimensions.depth,
        "height": 2.8,
        "doors": [
            {
                "wall": door.wall.value,
                "offset": door.offset,
                "width": door.width,
            }
            for door in request.doors
        ],
        "windows": [
            {
                "wall": window.wall.value,
                "offset": window.offset,
                "width": window.width,
            }
            for window in request.windows
        ],
        "direction": request.direction or "north",
        "budget_level": request.budget_level,
        "style": request.style,
        "user_preferences": request.user_preferences or {},
    }

    async def event_generator() -> AsyncGenerator[str, None]:
        async for event in orchestrator.run(room_spec, mode=mode):
            yield event.to_sse()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint for layout service."""
    return {"status": "healthy", "service": "layout"}
