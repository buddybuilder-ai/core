"""Layout API endpoints for 3D furniture generation."""

from typing import Any

from fastapi import APIRouter, Depends

from src.schemas.layout import DesignRequest, DesignResponse, FurnitureItem

router = APIRouter(prefix="/layout", tags=["Layout"])


async def get_layout_service() -> Any:
    """Dependency injection stub for layout service.

    Will be replaced with actual service injection later.
    """
    return None


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
