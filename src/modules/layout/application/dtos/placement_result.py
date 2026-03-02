"""Placement result DTOs for feng shui layout generation."""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from src.modules.layout.application.dtos.agent_context import (
    PlacedFurniture,
    PlacementStrategy,
)


class PlacementStatus(StrEnum):
    """Status of a placement operation."""

    SUCCESS = "success"
    PARTIAL = "partial"  # Some items placed, some failed
    FAILED = "failed"
    SKIPPED = "skipped"  # Item intentionally skipped


class PlacementFailureReason(StrEnum):
    """Reasons for placement failure."""

    NO_SPACE = "no_space"
    COLLISION = "collision"
    CLEARANCE_VIOLATION = "clearance_violation"
    OUT_OF_BOUNDS = "out_of_bounds"
    INVALID_ROTATION = "invalid_rotation"
    FENG_SHUI_VIOLATION = "feng_shui_violation"
    BLOCKED_EXIT = "blocked_exit"
    UNKNOWN = "unknown"


@dataclass
class PlacementAttempt:
    """Record of a single placement attempt.

    Attributes:
        furniture_id: ID of furniture being placed.
        furniture_name: Name of furniture.
        pos_x: Attempted X position.
        pos_z: Attempted Z position.
        rotation: Attempted rotation.
        strategy: Strategy used.
        success: Whether placement succeeded.
        failure_reason: Reason for failure if any.
        message: Human-readable message.
    """

    furniture_id: str
    furniture_name: str
    pos_x: float
    pos_z: float
    rotation: int
    strategy: PlacementStrategy
    success: bool
    failure_reason: PlacementFailureReason | None = None
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "furniture_id": self.furniture_id,
            "furniture_name": self.furniture_name,
            "position": {"x": self.pos_x, "z": self.pos_z},
            "rotation": self.rotation,
            "strategy": self.strategy.value,
            "success": self.success,
            "failure_reason": self.failure_reason.value if self.failure_reason else None,
            "message": self.message,
        }


@dataclass
class FallbackAction:
    """A fallback action taken during placement.

    Attributes:
        action_type: Type of fallback (move, rotate, resize, skip).
        original_pos: Original position attempted.
        new_pos: New position after fallback.
        original_rotation: Original rotation.
        new_rotation: New rotation after fallback.
        reason: Why fallback was needed.
        success: Whether fallback succeeded.
    """

    action_type: str
    original_pos: tuple[float, float]
    new_pos: tuple[float, float] | None
    original_rotation: int
    new_rotation: int
    reason: str
    success: bool

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "action_type": self.action_type,
            "original_position": {"x": self.original_pos[0], "z": self.original_pos[1]},
            "new_position": (
                {"x": self.new_pos[0], "z": self.new_pos[1]} if self.new_pos else None
            ),
            "original_rotation": self.original_rotation,
            "new_rotation": self.new_rotation,
            "reason": self.reason,
            "success": self.success,
        }


@dataclass
class PlacementResult:
    """Result of a single furniture placement operation.

    Attributes:
        furniture: The placed furniture item (if successful).
        status: Status of the placement.
        attempts: List of placement attempts made.
        fallback_actions: Fallback actions taken.
        final_strategy: Final strategy that worked.
        feng_shui_impact: Impact on feng shui score.
    """

    furniture: PlacedFurniture | None
    status: PlacementStatus
    attempts: list[PlacementAttempt] = field(default_factory=list)
    fallback_actions: list[FallbackAction] = field(default_factory=list)
    final_strategy: PlacementStrategy | None = None
    feng_shui_impact: float = 0.0

    @property
    def is_success(self) -> bool:
        """Check if placement was successful."""
        return self.status == PlacementStatus.SUCCESS

    @property
    def attempt_count(self) -> int:
        """Get number of attempts made."""
        return len(self.attempts)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "furniture": self.furniture.to_dict() if self.furniture else None,
            "status": self.status.value,
            "attempts": [a.to_dict() for a in self.attempts],
            "fallback_actions": [f.to_dict() for f in self.fallback_actions],
            "final_strategy": self.final_strategy.value if self.final_strategy else None,
            "feng_shui_impact": self.feng_shui_impact,
        }


@dataclass
class BatchPlacementResult:
    """Result of placing multiple furniture items.

    Attributes:
        results: Individual placement results.
        total_items: Total items to place.
        placed_count: Number successfully placed.
        failed_count: Number that failed.
        skipped_count: Number skipped.
        overall_status: Overall batch status.
        execution_time_ms: Total execution time.
    """

    results: list[PlacementResult] = field(default_factory=list)
    total_items: int = 0
    placed_count: int = 0
    failed_count: int = 0
    skipped_count: int = 0
    overall_status: PlacementStatus = PlacementStatus.SUCCESS
    execution_time_ms: float = 0.0

    @property
    def success_rate(self) -> float:
        """Get success rate as fraction."""
        if self.total_items == 0:
            return 0.0
        return self.placed_count / self.total_items

    @property
    def all_essential_placed(self) -> bool:
        """Check if all essential items were placed."""
        for result in self.results:
            if result.furniture and result.furniture.is_essential:
                if not result.is_success:
                    return False
        return True

    def get_placed_furniture(self) -> list[PlacedFurniture]:
        """Get all successfully placed furniture."""
        return [r.furniture for r in self.results if r.furniture and r.is_success]

    def get_failed_items(self) -> list[PlacementResult]:
        """Get all failed placement results."""
        return [r for r in self.results if r.status == PlacementStatus.FAILED]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "results": [r.to_dict() for r in self.results],
            "summary": {
                "total_items": self.total_items,
                "placed_count": self.placed_count,
                "failed_count": self.failed_count,
                "skipped_count": self.skipped_count,
                "success_rate": self.success_rate,
            },
            "overall_status": self.overall_status.value,
            "execution_time_ms": self.execution_time_ms,
        }


@dataclass
class LayoutOutput:
    """Final layout output for API response.

    Attributes:
        room_type: Type of room.
        room_dimensions: Room dimensions.
        furniture: List of placed furniture.
        feng_shui_score: Overall feng shui score.
        score_breakdown: Breakdown of score components.
        recommendations: Feng shui recommendations.
        warnings: Any warnings about the layout.
        metadata: Additional metadata.
    """

    room_type: str
    room_dimensions: dict[str, float]
    furniture: list[PlacedFurniture]
    feng_shui_score: float
    score_breakdown: dict[str, float] = field(default_factory=dict)
    recommendations: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON response."""
        return {
            "room_type": self.room_type,
            "room_dimensions": self.room_dimensions,
            "furniture": [f.to_dict() for f in self.furniture],
            "feng_shui_score": self.feng_shui_score,
            "score_breakdown": self.score_breakdown,
            "recommendations": self.recommendations,
            "warnings": self.warnings,
            "metadata": self.metadata,
        }

    def to_json_layout(self) -> dict[str, Any]:
        """Convert to simplified JSON layout format."""
        return {
            "room": {
                "type": self.room_type,
                "width": self.room_dimensions.get("width", 0),
                "depth": self.room_dimensions.get("depth", 0),
            },
            "items": [
                {
                    "id": f.id,
                    "name": f.name,
                    "category": f.category,
                    "x": f.pos_x,
                    "z": f.pos_z,
                    "width": f.width,
                    "depth": f.depth,
                    "height": f.height,
                    "rotation": f.rotation,
                }
                for f in self.furniture
            ],
            "score": self.feng_shui_score,
        }
