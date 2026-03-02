"""Layout schemas for 3D furniture generation."""

from pydantic import BaseModel, Field

from src.schemas.layout.agent import (
    AgentContext,
    AgentExecutionTrace,
    AgentStep,
    FengShuiLayoutRequest,
    FengShuiLayoutResponse,
    LayoutConstraint,
    LayoutMetadata,
    PlacedFurnitureItem,
    ToolCallResult,
)

# Import from base first (no circular dependency)
from src.schemas.layout.base import RoomDimensions

# Then import from submodules
from src.schemas.layout.feng_shui import (
    CommandPosition,
    DoorPosition,
    ElementBalance,
    FengShuiAnalysis,
    FengShuiRecommendation,
    FengShuiRule,
    FengShuiScoreBreakdown,
    FiveElement,
    FurnitureDimensions,
    RoomType,
    RulePriority,
    ShaChiLine,
    WallSide,
    WindowPosition,
)


class DesignRequest(BaseModel):
    """Request schema for layout generation."""

    dimensions: RoomDimensions = Field(..., description="Room dimensions")
    style: str = Field(..., min_length=1, description="Interior design style")
    requirements: str = Field(..., description="Additional requirements")


class FurnitureItem(BaseModel):
    """Single furniture item with position and rotation."""

    id: str = Field(..., description="Furniture item identifier")
    pos_x: float = Field(..., description="X position in meters")
    pos_y: float = Field(..., description="Y position (height) in meters")
    pos_z: float = Field(..., description="Z position in meters")
    rotation: float = Field(..., description="Rotation in degrees")


class DesignResponse(BaseModel):
    """Response schema for layout generation."""

    items: list[FurnitureItem] = Field(default_factory=list, description="List of furniture items")
    reasoning: str = Field(..., description="AI reasoning for the layout")


__all__ = [
    # Original schemas
    "RoomDimensions",
    "DesignRequest",
    "FurnitureItem",
    "DesignResponse",
    # Feng Shui schemas
    "CommandPosition",
    "DoorPosition",
    "ElementBalance",
    "FengShuiAnalysis",
    "FengShuiRecommendation",
    "FengShuiRule",
    "FengShuiScoreBreakdown",
    "FiveElement",
    "FurnitureDimensions",
    "RoomType",
    "RulePriority",
    "ShaChiLine",
    "WallSide",
    "WindowPosition",
    # Agent schemas
    "AgentContext",
    "AgentExecutionTrace",
    "AgentStep",
    "FengShuiLayoutRequest",
    "FengShuiLayoutResponse",
    "LayoutConstraint",
    "LayoutMetadata",
    "PlacedFurnitureItem",
    "ToolCallResult",
]
