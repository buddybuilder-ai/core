"""Feng shui specific Pydantic schemas."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class RoomType(str, Enum):
    """Supported room types for feng shui analysis."""

    BEDROOM = "bedroom"
    LIVING_ROOM = "living_room"
    OFFICE = "office"
    DINING_ROOM = "dining_room"
    KITCHEN = "kitchen"
    BATHROOM = "bathroom"


class FiveElement(str, Enum):
    """Five elements in feng shui."""

    WOOD = "wood"
    FIRE = "fire"
    EARTH = "earth"
    METAL = "metal"
    WATER = "water"


class RulePriority(int, Enum):
    """Feng shui rule priority levels."""

    MUST_NOT_VIOLATE = 1
    SHOULD_DO = 2
    RECOMMENDED = 3


class WallSide(str, Enum):
    """Wall sides for positioning doors and windows."""

    NORTH = "north"
    SOUTH = "south"
    EAST = "east"
    WEST = "west"


class DoorPosition(BaseModel):
    """Door position in the room.

    Attributes:
        wall: Wall side where door is located.
        offset: Distance from wall start in meters.
        width: Door width in meters.
        swing_inward: Whether door swings inward.
    """

    wall: WallSide = Field(..., description="Wall side where door is located")
    offset: float = Field(..., ge=0, description="Offset from wall start in meters")
    width: float = Field(default=0.9, gt=0, description="Door width in meters")
    swing_inward: bool = Field(default=True, description="Whether door swings inward")


class WindowPosition(BaseModel):
    """Window position in the room.

    Attributes:
        wall: Wall side where window is located.
        offset: Distance from wall start in meters.
        width: Window width in meters.
        height: Window height in meters.
        sill_height: Height from floor to window sill.
    """

    wall: WallSide = Field(..., description="Wall side where window is located")
    offset: float = Field(..., ge=0, description="Offset from wall start in meters")
    width: float = Field(..., gt=0, description="Window width in meters")
    height: float = Field(default=1.2, gt=0, description="Window height in meters")
    sill_height: float = Field(
        default=0.9, ge=0, description="Height from floor to window sill"
    )


class FurnitureDimensions(BaseModel):
    """Physical dimensions of furniture.

    Attributes:
        width: Width (x-axis) in meters.
        depth: Depth (z-axis) in meters.
        height: Height (y-axis) in meters.
    """

    width: float = Field(..., gt=0, description="Width in meters (X-axis)")
    depth: float = Field(..., gt=0, description="Depth in meters (Z-axis)")
    height: float = Field(..., gt=0, description="Height in meters (Y-axis)")

    @property
    def floor_area(self) -> float:
        """Calculate floor area in square meters."""
        return self.width * self.depth


class FengShuiRule(BaseModel):
    """A feng shui rule from knowledge base.

    Attributes:
        rule_id: Unique rule identifier.
        description: Human-readable rule description.
        priority: Rule priority level.
        room_types: Applicable room types.
        furniture_categories: Applicable furniture categories.
        source: Knowledge source reference.
    """

    rule_id: str = Field(..., description="Unique rule identifier")
    description: str = Field(..., description="Rule description")
    priority: RulePriority = Field(..., description="Rule priority level")
    room_types: list[RoomType] = Field(
        default_factory=list, description="Applicable room types"
    )
    furniture_categories: list[str] | None = Field(
        default=None, description="Applicable furniture categories"
    )
    source: str | None = Field(default=None, description="Knowledge source reference")

    @field_validator("description")
    @classmethod
    def description_not_empty(cls, v: str) -> str:
        """Validate description is not empty."""
        if not v.strip():
            msg = "Description cannot be empty"
            raise ValueError(msg)
        return v


class FengShuiScoreBreakdown(BaseModel):
    """Detailed feng shui score breakdown.

    Scoring components:
    - command_position: 0-30 points
    - five_elements_balance: 0-20 points
    - chi_flow: 0-25 points
    - sha_chi_avoidance: 0-25 points

    Total possible: 100 points
    """

    command_position: int = Field(
        ..., ge=0, le=30, description="Command position score (0-30)"
    )
    five_elements_balance: int = Field(
        ..., ge=0, le=20, description="Five elements balance score (0-20)"
    )
    chi_flow: int = Field(..., ge=0, le=25, description="Chi flow score (0-25)")
    sha_chi_avoidance: int = Field(
        ..., ge=0, le=25, description="Sha chi avoidance score (0-25)"
    )

    @property
    def total(self) -> int:
        """Calculate total feng shui score (0-100)."""
        return (
            self.command_position
            + self.five_elements_balance
            + self.chi_flow
            + self.sha_chi_avoidance
        )

    @property
    def grade(self) -> str:
        """Get letter grade based on total score."""
        total = self.total
        if total >= 90:
            return "A"
        if total >= 70:
            return "B"
        if total >= 50:
            return "C"
        if total >= 40:
            return "D"
        return "F"

    @property
    def is_acceptable(self) -> bool:
        """Check if score meets minimum acceptable threshold (>=40)."""
        return self.total >= 40


class FengShuiRecommendation(BaseModel):
    """A feng shui recommendation for improvement.

    Attributes:
        category: Recommendation category.
        description: What to do.
        priority: How important this recommendation is.
        expected_improvement: Expected score improvement.
    """

    category: str = Field(..., description="Recommendation category")
    description: str = Field(..., description="What to do")
    priority: RulePriority = Field(
        default=RulePriority.RECOMMENDED, description="Importance level"
    )
    expected_improvement: int = Field(
        default=0, ge=0, description="Expected score improvement"
    )


class ElementBalance(BaseModel):
    """Balance of five elements in the layout.

    Attributes:
        wood: Wood element count/presence.
        fire: Fire element count/presence.
        earth: Earth element count/presence.
        metal: Metal element count/presence.
        water: Water element count/presence.
    """

    wood: int = Field(default=0, ge=0, description="Wood element count")
    fire: int = Field(default=0, ge=0, description="Fire element count")
    earth: int = Field(default=0, ge=0, description="Earth element count")
    metal: int = Field(default=0, ge=0, description="Metal element count")
    water: int = Field(default=0, ge=0, description="Water element count")

    @property
    def total_elements(self) -> int:
        """Total number of element instances."""
        return self.wood + self.fire + self.earth + self.metal + self.water

    @property
    def unique_elements(self) -> int:
        """Count of unique elements present."""
        return sum(1 for e in [self.wood, self.fire, self.earth, self.metal, self.water] if e > 0)

    @property
    def is_balanced(self) -> bool:
        """Check if elements are reasonably balanced (at least 3 present)."""
        return self.unique_elements >= 3

    def to_dict(self) -> dict[str, int]:
        """Convert to dictionary."""
        return {
            "wood": self.wood,
            "fire": self.fire,
            "earth": self.earth,
            "metal": self.metal,
            "water": self.water,
        }


class CommandPosition(BaseModel):
    """Command position analysis result.

    Attributes:
        furniture_id: ID of furniture in command position.
        is_in_position: Whether furniture is in command position.
        can_see_door: Whether furniture has view of door.
        has_wall_backing: Whether furniture has solid wall behind.
        distance_from_ideal: Distance from ideal position in meters.
    """

    furniture_id: str = Field(..., description="Furniture ID")
    is_in_position: bool = Field(
        default=False, description="Whether in command position"
    )
    can_see_door: bool = Field(default=False, description="Has view of door")
    has_wall_backing: bool = Field(default=False, description="Has solid wall behind")
    distance_from_ideal: float = Field(
        default=0, ge=0, description="Distance from ideal position in meters"
    )


class ShaChiLine(BaseModel):
    """A sha chi (negative energy) line in the room.

    Sha chi lines are direct lines between openings (doors, windows)
    that should be avoided for furniture placement.

    Attributes:
        from_element: Starting element (door/window ID).
        to_element: Ending element (door/window ID).
        intensity: Intensity of negative energy (1-10).
        mitigation: Suggested mitigation strategy.
    """

    from_element: str = Field(..., description="Starting element ID")
    to_element: str = Field(..., description="Ending element ID")
    intensity: int = Field(default=5, ge=1, le=10, description="Intensity (1-10)")
    mitigation: str | None = Field(
        default=None, description="Suggested mitigation strategy"
    )


class FengShuiAnalysis(BaseModel):
    """Complete feng shui analysis for a layout.

    Attributes:
        score: Score breakdown.
        command_positions: Command position analysis for key furniture.
        element_balance: Five elements balance.
        sha_chi_lines: Detected sha chi lines.
        recommendations: Improvement recommendations.
        warnings: Critical warnings.
        metadata: Additional analysis metadata.
    """

    score: FengShuiScoreBreakdown = Field(..., description="Score breakdown")
    command_positions: list[CommandPosition] = Field(
        default_factory=list, description="Command position analysis"
    )
    element_balance: ElementBalance = Field(
        default_factory=ElementBalance, description="Five elements balance"
    )
    sha_chi_lines: list[ShaChiLine] = Field(
        default_factory=list, description="Detected sha chi lines"
    )
    recommendations: list[FengShuiRecommendation] = Field(
        default_factory=list, description="Improvement recommendations"
    )
    warnings: list[str] = Field(default_factory=list, description="Critical warnings")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata"
    )
