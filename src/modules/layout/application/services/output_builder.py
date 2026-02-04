"""Output builder service for layout generation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.modules.layout.application.dtos import (
    AgentContext,
    PlacedFurniture,
)
from src.modules.layout.application.dtos.placement_result import (
    BatchPlacementResult,
    LayoutOutput,
    PlacementStatus,
)
from src.modules.layout.application.services.feng_shui_scorer import ScoringResult
from src.modules.layout.domain.entities import Room
from src.modules.layout.domain.value_objects import FengShuiScore


@dataclass
class OutputConfig:
    """Configuration for output building.

    Attributes:
        include_metadata: Whether to include metadata in output.
        include_recommendations: Whether to include feng shui recommendations.
        include_warnings: Whether to include warnings.
        include_placement_details: Whether to include detailed placement info.
        max_recommendations: Maximum number of recommendations to include.
        json_indent: Indentation for JSON output (None for compact).
    """

    include_metadata: bool = True
    include_recommendations: bool = True
    include_warnings: bool = True
    include_placement_details: bool = False
    max_recommendations: int = 5
    json_indent: int | None = 2


@dataclass
class OutputSummary:
    """Summary of the output generation.

    Attributes:
        total_items: Total furniture items in layout.
        essential_items: Count of essential items.
        optional_items: Count of optional items.
        feng_shui_score: Overall feng shui score.
        feng_shui_grade: Letter grade.
        has_warnings: Whether there are warnings.
        warning_count: Number of warnings.
    """

    total_items: int = 0
    essential_items: int = 0
    optional_items: int = 0
    feng_shui_score: int = 0
    feng_shui_grade: str = "F"
    has_warnings: bool = False
    warning_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "total_items": self.total_items,
            "essential_items": self.essential_items,
            "optional_items": self.optional_items,
            "feng_shui_score": self.feng_shui_score,
            "feng_shui_grade": self.feng_shui_grade,
            "has_warnings": self.has_warnings,
            "warning_count": self.warning_count,
        }


class OutputBuilder:
    """Service for building the final layout output.

    This service is responsible for:
    - Creating the final layout output structure
    - Formatting furniture placements for API response
    - Including feng shui recommendations
    - Adding warnings and metadata
    - Supporting multiple output formats
    """

    def __init__(self, config: OutputConfig | None = None) -> None:
        """Initialize the output builder.

        Args:
            config: Output configuration.
        """
        self.config = config or OutputConfig()

    def build_output(
        self,
        room: Room,
        placed_furniture: list[PlacedFurniture],
        feng_shui_score: FengShuiScore | None = None,
        scoring_result: ScoringResult | None = None,
        placement_result: BatchPlacementResult | None = None,
    ) -> LayoutOutput:
        """Build the final layout output.

        Args:
            room: The room being designed.
            placed_furniture: List of placed furniture items.
            feng_shui_score: The feng shui score.
            scoring_result: Detailed scoring result.
            placement_result: Batch placement result.

        Returns:
            LayoutOutput with complete layout information.
        """
        # Get score value
        score_value = feng_shui_score.total if feng_shui_score else 0

        # Build score breakdown
        score_breakdown = {}
        if feng_shui_score:
            score_breakdown = {
                "command_position": feng_shui_score.command_position,
                "five_elements": feng_shui_score.five_elements,
                "chi_flow": feng_shui_score.chi_flow,
                "sha_chi_avoidance": feng_shui_score.sha_chi_avoidance,
            }

        # Build recommendations
        recommendations = []
        if self.config.include_recommendations:
            recommendations = self._build_recommendations(
                feng_shui_score, scoring_result
            )

        # Build warnings
        warnings = []
        if self.config.include_warnings:
            warnings = self._build_warnings(
                placed_furniture, feng_shui_score, placement_result
            )

        # Build metadata
        metadata = {}
        if self.config.include_metadata:
            metadata = self._build_metadata(
                room, placed_furniture, feng_shui_score, placement_result
            )

        return LayoutOutput(
            room_type=room.room_type.value,
            room_dimensions={
                "width": room.width,
                "depth": room.depth,
                "height": room.height,
            },
            furniture=placed_furniture,
            feng_shui_score=float(score_value),
            score_breakdown=score_breakdown,
            recommendations=recommendations,
            warnings=warnings,
            metadata=metadata,
        )

    def build_from_context(self, context: AgentContext) -> LayoutOutput:
        """Build output from agent context.

        Args:
            context: Agent context with all layout data.

        Returns:
            LayoutOutput with complete layout information.
        """
        return self.build_output(
            room=context.room,
            placed_furniture=context.placed_furniture,
            feng_shui_score=context.feng_shui_score,
        )

    def _build_recommendations(
        self,
        score: FengShuiScore | None,
        scoring_result: ScoringResult | None,
    ) -> list[str]:
        """Build feng shui recommendations."""
        recommendations: list[str] = []

        # Get recommendations from scoring result
        if scoring_result and scoring_result.recommendations:
            recommendations.extend(scoring_result.recommendations)

        # Get recommendations from score
        if score:
            score_recommendations = score.get_improvement_suggestions()
            for rec in score_recommendations:
                if rec not in recommendations:
                    recommendations.append(rec)

        # Limit recommendations
        return recommendations[: self.config.max_recommendations]

    def _build_warnings(
        self,
        furniture: list[PlacedFurniture],
        score: FengShuiScore | None,
        placement_result: BatchPlacementResult | None,
    ) -> list[str]:
        """Build warnings for the layout."""
        warnings: list[str] = []

        # Check for low score
        if score and score.total < 40:
            warnings.append(
                f"Low feng shui score: {score.total}/100. Consider repositioning furniture."
            )

        # Check placement result
        if placement_result:
            if placement_result.failed_count > 0:
                warnings.append(
                    f"{placement_result.failed_count} item(s) could not be placed."
                )

            if not placement_result.all_essential_placed:
                warnings.append(
                    "Not all essential furniture could be placed. "
                    "Consider a larger room or fewer items."
                )

        # Check for empty layout
        if not furniture:
            warnings.append("No furniture was placed in the layout.")

        # Check for missing essential categories
        essential_categories = {"bed", "desk", "sofa"}
        placed_categories = {f.category for f in furniture}
        essential_placed = essential_categories.intersection(placed_categories)

        if not essential_placed:
            warnings.append("No essential furniture (bed/desk/sofa) in layout.")

        return warnings

    def _build_metadata(
        self,
        room: Room,
        furniture: list[PlacedFurniture],
        score: FengShuiScore | None,
        placement_result: BatchPlacementResult | None,
    ) -> dict[str, Any]:
        """Build metadata for the output."""
        metadata: dict[str, Any] = {}

        # Room metadata
        metadata["room"] = {
            "area": room.width * room.depth,
            "door_count": len(room.doors),
            "window_count": len(room.windows),
        }

        # Furniture metadata
        essential_count = sum(1 for f in furniture if f.is_essential)
        optional_count = len(furniture) - essential_count
        total_furniture_area = sum(f.width * f.depth for f in furniture)

        metadata["furniture"] = {
            "total_count": len(furniture),
            "essential_count": essential_count,
            "optional_count": optional_count,
            "total_area": round(total_furniture_area, 2),
            "coverage_ratio": round(
                total_furniture_area / (room.width * room.depth), 2
            ),
        }

        # Score metadata
        if score:
            metadata["score"] = {
                "total": score.total,
                "grade": score.grade,
                "is_acceptable": score.is_acceptable,
                "is_good": score.is_good,
                "weakest_component": score.get_weakest_component(),
            }

        # Placement metadata
        if placement_result and self.config.include_placement_details:
            metadata["placement"] = {
                "total_attempts": sum(
                    len(r.attempts) for r in placement_result.results
                ),
                "success_rate": round(placement_result.success_rate, 2),
                "execution_time_ms": round(placement_result.execution_time_ms, 2),
            }

        return metadata

    def get_summary(
        self,
        furniture: list[PlacedFurniture],
        score: FengShuiScore | None,
        warnings: list[str] | None = None,
    ) -> OutputSummary:
        """Get a summary of the output.

        Args:
            furniture: List of placed furniture.
            score: Feng shui score.
            warnings: List of warnings.

        Returns:
            OutputSummary with key metrics.
        """
        essential_count = sum(1 for f in furniture if f.is_essential)

        return OutputSummary(
            total_items=len(furniture),
            essential_items=essential_count,
            optional_items=len(furniture) - essential_count,
            feng_shui_score=score.total if score else 0,
            feng_shui_grade=score.grade if score else "F",
            has_warnings=bool(warnings),
            warning_count=len(warnings) if warnings else 0,
        )

    def format_as_json(self, output: LayoutOutput) -> dict[str, Any]:
        """Format output as JSON-serializable dictionary.

        Args:
            output: Layout output to format.

        Returns:
            JSON-serializable dictionary.
        """
        return output.to_dict()

    def format_as_simple_json(self, output: LayoutOutput) -> dict[str, Any]:
        """Format output as simplified JSON for frontend.

        Args:
            output: Layout output to format.

        Returns:
            Simplified JSON-serializable dictionary.
        """
        return output.to_json_layout()

    def format_furniture_for_api(
        self,
        furniture: list[PlacedFurniture],
    ) -> list[dict[str, Any]]:
        """Format furniture list for API response.

        Args:
            furniture: List of placed furniture.

        Returns:
            List of furniture dictionaries.
        """
        return [
            {
                "id": f.id,
                "name": f.name,
                "category": f.category,
                "position": {
                    "x": round(f.pos_x, 3),
                    "y": 0,  # Floor level
                    "z": round(f.pos_z, 3),
                },
                "dimensions": {
                    "width": round(f.width, 3),
                    "height": round(f.height, 3),
                    "depth": round(f.depth, 3),
                },
                "rotation": f.rotation,
                "is_essential": f.is_essential,
            }
            for f in furniture
        ]

    def update_context(
        self,
        context: AgentContext,
        output: LayoutOutput,
    ) -> None:
        """Update agent context with output information.

        Args:
            context: Agent context to update.
            output: Generated layout output.
        """
        # Store output in metadata
        context.metadata["output"] = {
            "feng_shui_score": output.feng_shui_score,
            "score_breakdown": output.score_breakdown,
            "recommendation_count": len(output.recommendations),
            "warning_count": len(output.warnings),
            "furniture_count": len(output.furniture),
        }

        # Add any new warnings to context
        for warning in output.warnings:
            if warning not in context.validation_warnings:
                context.add_warning(warning)


@dataclass
class LayoutReport:
    """Detailed report of the layout generation.

    Attributes:
        output: The layout output.
        summary: Output summary.
        success: Whether generation was successful.
        error_message: Error message if failed.
    """

    output: LayoutOutput | None
    summary: OutputSummary
    success: bool = True
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "error_message": self.error_message,
            "summary": self.summary.to_dict(),
            "output": self.output.to_dict() if self.output else None,
        }


def build_layout_report(
    context: AgentContext,
    placement_result: BatchPlacementResult | None = None,
    scoring_result: ScoringResult | None = None,
) -> LayoutReport:
    """Build a complete layout report from context.

    Args:
        context: Agent context with layout data.
        placement_result: Placement result.
        scoring_result: Scoring result.

    Returns:
        LayoutReport with complete information.
    """
    builder = OutputBuilder()

    try:
        output = builder.build_output(
            room=context.room,
            placed_furniture=context.placed_furniture,
            feng_shui_score=context.feng_shui_score,
            scoring_result=scoring_result,
            placement_result=placement_result,
        )

        summary = builder.get_summary(
            furniture=context.placed_furniture,
            score=context.feng_shui_score,
            warnings=output.warnings,
        )

        return LayoutReport(
            output=output,
            summary=summary,
            success=True,
        )

    except Exception as e:
        return LayoutReport(
            output=None,
            summary=OutputSummary(),
            success=False,
            error_message=str(e),
        )
