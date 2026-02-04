"""Layout API endpoints for 3D furniture generation."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from src.modules.layout.application.agent import (
    LayoutOrchestrator,
    LayoutRequest as OrchestratorRequest,
    OrchestratorConfig,
)
from src.schemas.layout import (
    DesignRequest,
    DesignResponse,
    FengShuiLayoutRequest,
    FengShuiLayoutResponse,
    FengShuiScoreBreakdown,
    FurnitureDimensions,
    FurnitureItem,
    LayoutMetadata,
    PlacedFurnitureItem,
)

router = APIRouter(prefix="/layout", tags=["Layout"])


async def get_layout_service() -> Any:
    """Dependency injection stub for layout service.

    Will be replaced with actual service injection later.
    """
    return None


def get_layout_orchestrator(use_llm: bool = False) -> LayoutOrchestrator:
    """Create and return a layout orchestrator.

    Args:
        use_llm: Whether to use LLM for intelligent scoring.

    Returns:
        Configured LayoutOrchestrator instance.
    """
    config = OrchestratorConfig(
        use_minimal_workflow=False,
        use_llm=use_llm,
        max_retries=3,
        min_acceptable_score=40,
        auto_retry_low_score=True,
    )
    return LayoutOrchestrator(config)


@router.post("/generate", response_model=DesignResponse)
async def generate_layout(
    request: DesignRequest,
    service: Any = Depends(get_layout_service),
) -> DesignResponse:
    """Generate a 3D furniture layout for the given room.

    Args:
        request: Design request with room dimensions, style, and requirements.
        service: Injected layout service (stub for now).

    Returns:
        DesignResponse with furniture items and AI reasoning.
    """
    # Mock response - will be replaced with actual LLM implementation
    return DesignResponse(
        items=[
            FurnitureItem(
                id="sofa_01",
                pos_x=2.0,
                pos_y=0.0,
                pos_z=1.5,
                rotation=0.0,
            ),
            FurnitureItem(
                id="coffee_table_01",
                pos_x=2.5,
                pos_y=0.0,
                pos_z=3.0,
                rotation=0.0,
            ),
            FurnitureItem(
                id="armchair_01",
                pos_x=4.0,
                pos_y=0.0,
                pos_z=1.5,
                rotation=270.0,
            ),
        ],
        reasoning=(
            f"Generated {request.style} style layout for "
            f"{request.dimensions.width}m x {request.dimensions.depth}m room. "
            f"Requirements: {request.requirements}"
        ),
    )


@router.post("/feng-shui", response_model=FengShuiLayoutResponse)
async def generate_feng_shui_layout(
    request: FengShuiLayoutRequest,
    use_llm: bool = False,
) -> FengShuiLayoutResponse:
    """Generate a feng shui optimized furniture layout.

    This endpoint uses AI-powered layout generation with feng shui principles
    including command position, five elements balance, chi flow, and sha chi
    avoidance.

    Args:
        request: Feng shui layout request with room dimensions and preferences.
        use_llm: Enable LLM-powered scoring for intelligent feng shui analysis.
            When enabled, uses OpenRouter API for enhanced scoring.
            Default: False (uses deterministic rule-based scoring).

    Returns:
        FengShuiLayoutResponse with placed furniture, feng shui score, and analysis.

    Raises:
        HTTPException: If layout generation fails.
    """
    orchestrator = get_layout_orchestrator(use_llm=use_llm)
    # Convert API request to orchestrator request
    # RoomDimensions only has width/depth, use default height
    orchestrator_request = OrchestratorRequest(
        room_type=request.room_type.value,
        width=request.dimensions.width,
        depth=request.dimensions.depth,
        height=2.8,  # Default ceiling height
        budget_level=request.budget_level,
        style_preference=request.style or "modern",
        doors=[
            {
                "wall": door.wall.value,
                "offset": door.offset,
                "width": door.width,
            }
            for door in request.doors
        ],
        windows=[
            {
                "wall": window.wall.value,
                "offset": window.offset,
                "width": window.width,
            }
            for window in request.windows
        ],
        custom_preferences=request.user_preferences or {},
    )

    # Generate layout
    response = await orchestrator.generate_layout(orchestrator_request)

    if not response.success:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=response.error_message or "Layout generation failed",
        )

    # Convert orchestrator response to API response
    items: list[PlacedFurnitureItem] = []
    if response.output:
        for furniture in response.output.furniture:
            items.append(
                PlacedFurnitureItem(
                    id=furniture.furniture_id,
                    name=furniture.name,
                    category=furniture.category,
                    pos_x=furniture.pos_x,
                    pos_y=0.0,
                    pos_z=furniture.pos_z,
                    rotation=float(furniture.rotation),
                    dimensions=FurnitureDimensions(
                        width=furniture.width,
                        depth=furniture.depth,
                        height=furniture.height,
                    ),
                    is_essential=furniture.is_essential,
                    feng_shui_notes=furniture.feng_shui_notes,
                )
            )

    # Build score breakdown
    score_breakdown = FengShuiScoreBreakdown(
        command_position=0,
        five_elements_balance=0,
        chi_flow=0,
        sha_chi_avoidance=0,
    )
    if response.output and response.output.score_breakdown:
        breakdown = response.output.score_breakdown
        score_breakdown = FengShuiScoreBreakdown(
            command_position=breakdown.get("command_position", 0),
            five_elements_balance=breakdown.get("five_elements", 0),
            chi_flow=breakdown.get("chi_flow", 0),
            sha_chi_avoidance=breakdown.get("sha_chi_avoidance", 0),
        )

    # Build reasoning
    reasoning = f"Generated feng shui layout for {request.room_type.value} room "
    reasoning += f"({request.dimensions.width}m x {request.dimensions.depth}m). "
    reasoning += f"Feng shui score: {response.feng_shui_score}/100 ({score_breakdown.grade}). "
    if response.furniture_count > 0:
        reasoning += f"Placed {response.furniture_count} furniture items."

    # Build warnings
    warnings: list[str] = []
    if response.output and response.output.recommendations:
        warnings.extend(response.output.recommendations[:3])  # Limit to 3 warnings

    # Check if LLM was used from phase results
    llm_used = False
    for phase_result in response.phase_results:
        if phase_result.data and phase_result.data.get("llm_used"):
            llm_used = True
            break

    # Add LLM info to reasoning
    if llm_used:
        reasoning += " [LLM-powered scoring]"

    return FengShuiLayoutResponse(
        items=items,
        feng_shui_score=score_breakdown,
        reasoning=reasoning,
        warnings=warnings,
        metadata=LayoutMetadata(
            generation_time_ms=int(response.execution_time_ms),
            agent_model="openrouter/llm" if llm_used else None,
        ),
    )


@router.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint for layout service.

    Returns:
        Health status.
    """
    return {"status": "healthy", "service": "layout"}
