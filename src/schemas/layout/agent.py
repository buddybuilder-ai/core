"""Agent request and response Pydantic schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator

from src.schemas.layout.base import RoomDimensions
from src.schemas.layout.feng_shui import (
    DoorPosition,
    FengShuiAnalysis,
    FengShuiScoreBreakdown,
    FurnitureDimensions,
    RoomType,
    WindowPosition,
)


class FengShuiLayoutRequest(BaseModel):
    """Request for feng shui layout generation.

    Attributes:
        dimensions: Room dimensions in meters.
        room_type: Type of room (bedroom, office, etc.).
        doors: List of door positions.
        windows: List of window positions.
        style: Optional preferred design style.
        user_preferences: Optional user-specific preferences.
        budget_level: Budget constraint (low/medium/high).
        direction: Room's facing direction for feng shui.
    """

    dimensions: RoomDimensions = Field(..., description="Room dimensions in meters")
    room_type: RoomType = Field(..., description="Type of room")
    doors: list[DoorPosition] = Field(default_factory=list, description="Door positions")
    windows: list[WindowPosition] = Field(default_factory=list, description="Window positions")
    style: str | None = Field(default=None, description="Preferred design style")
    user_preferences: dict[str, Any] | None = Field(
        default=None, description="User-specific preferences"
    )
    budget_level: str = Field(default="medium", description="Budget level: low/medium/high")
    direction: str = Field(default="north", description="Room's facing direction for feng shui")

    @model_validator(mode="after")
    def validate_budget_level(self) -> FengShuiLayoutRequest:
        """Validate budget level is valid."""
        valid_levels = {"low", "medium", "high"}
        if self.budget_level not in valid_levels:
            msg = f"budget_level must be one of {valid_levels}, got '{self.budget_level}'"
            raise ValueError(msg)
        return self


class PlacedFurnitureItem(BaseModel):
    """Furniture item with placement details.

    Attributes:
        id: Unique furniture item identifier.
        name: Human-readable furniture name.
        category: Furniture category.
        pos_x: X position in meters (width axis).
        pos_y: Y position in meters (height axis, usually 0).
        pos_z: Z position in meters (depth axis).
        rotation: Rotation angle in degrees (0, 90, 180, 270).
        dimensions: Item dimensions.
        is_essential: Whether this is essential furniture.
        feng_shui_notes: Feng shui notes for this placement.
    """

    id: str = Field(..., description="Furniture catalog ID")
    name: str = Field(..., description="Human-readable name")
    category: str = Field(..., description="Furniture category")
    pos_x: float = Field(..., description="X position in meters")
    pos_y: float = Field(default=0.0, description="Y position (height) in meters")
    pos_z: float = Field(..., description="Z position in meters")
    rotation: float = Field(default=0.0, ge=0, lt=360, description="Rotation in degrees")
    dimensions: FurnitureDimensions = Field(..., description="Item dimensions")
    is_essential: bool = Field(default=True, description="Essential vs optional")
    feng_shui_notes: list[str] = Field(
        default_factory=list, description="Feng shui placement notes"
    )


class LayoutConstraint(BaseModel):
    """Constraint applied during layout generation.

    Attributes:
        constraint_type: Type of constraint.
        description: Human-readable constraint description.
        satisfied: Whether the constraint is satisfied.
        severity: Constraint severity (error/warning/info).
    """

    constraint_type: str = Field(..., description="Type: clearance/collision/feng_shui/safety")
    description: str = Field(..., description="Constraint description")
    satisfied: bool = Field(..., description="Whether constraint is satisfied")
    severity: str = Field(default="warning", description="Severity: error/warning/info")


class LayoutMetadata(BaseModel):
    """Metadata for generated layout.

    Attributes:
        layout_id: Unique layout identifier.
        generated_at: Generation timestamp.
        version: Layout schema version.
        generation_time_ms: Time taken to generate in milliseconds.
        retries: Number of retry attempts made.
        agent_model: LLM model used for generation.
    """

    layout_id: str = Field(default_factory=lambda: str(uuid4()), description="Unique layout ID")
    generated_at: datetime = Field(
        default_factory=datetime.utcnow, description="Generation timestamp"
    )
    version: str = Field(default="1.0", description="Layout schema version")
    generation_time_ms: int = Field(default=0, ge=0, description="Generation time in milliseconds")
    retries: int = Field(default=0, ge=0, description="Number of retries")
    agent_model: str | None = Field(default=None, description="LLM model used")


class FengShuiLayoutResponse(BaseModel):
    """Complete response for feng shui layout generation.

    Attributes:
        items: List of placed furniture items.
        feng_shui_score: Feng shui score breakdown.
        feng_shui_analysis: Detailed feng shui analysis.
        constraints: Applied constraints and their status.
        reasoning: AI reasoning for the layout decisions.
        warnings: Any warnings encountered during generation.
        skipped_items: Furniture that couldn't be placed.
        metadata: Layout generation metadata.
    """

    items: list[PlacedFurnitureItem] = Field(
        default_factory=list, description="Placed furniture items"
    )
    feng_shui_score: FengShuiScoreBreakdown = Field(..., description="Feng shui score breakdown")
    feng_shui_analysis: FengShuiAnalysis | None = Field(
        default=None, description="Detailed feng shui analysis"
    )
    constraints: list[LayoutConstraint] = Field(
        default_factory=list, description="Applied constraints"
    )
    reasoning: str = Field(..., description="AI reasoning explanation")
    warnings: list[str] = Field(default_factory=list, description="Generation warnings")
    skipped_items: list[str] = Field(
        default_factory=list, description="Furniture that couldn't be placed"
    )
    metadata: LayoutMetadata = Field(
        default_factory=LayoutMetadata, description="Generation metadata"
    )

    @property
    def success(self) -> bool:
        """Check if layout generation was successful."""
        return (
            len(self.items) > 0
            and self.feng_shui_score.is_acceptable
            and not any(c.severity == "error" and not c.satisfied for c in self.constraints)
        )

    @property
    def furniture_count(self) -> int:
        """Count of placed furniture items."""
        return len(self.items)

    @property
    def essential_count(self) -> int:
        """Count of essential furniture items placed."""
        return sum(1 for item in self.items if item.is_essential)


class AgentContext(BaseModel):
    """Context for agent execution.

    Attributes:
        session_id: Current session identifier.
        user_id: User identifier for preference lookup.
        previous_scores: Scores from previous attempts.
        max_retries: Maximum retry attempts allowed.
        strict_mode: Whether to enforce all feng shui rules.
        debug: Enable debug logging.
    """

    session_id: str = Field(default_factory=lambda: str(uuid4()), description="Session ID")
    user_id: str | None = Field(default=None, description="User ID")
    previous_scores: list[int] = Field(default_factory=list, description="Previous attempt scores")
    max_retries: int = Field(default=3, ge=1, le=10, description="Max retry attempts")
    strict_mode: bool = Field(default=False, description="Enforce all feng shui rules")
    debug: bool = Field(default=False, description="Enable debug mode")

    def record_attempt(self, score: int) -> None:
        """Record an attempt score.

        Args:
            score: The feng shui score for this attempt.
        """
        self.previous_scores.append(score)

    @property
    def attempt_count(self) -> int:
        """Number of attempts made."""
        return len(self.previous_scores)

    @property
    def best_score(self) -> int | None:
        """Best score achieved so far."""
        return max(self.previous_scores) if self.previous_scores else None

    @property
    def should_retry(self) -> bool:
        """Check if retry is warranted based on scores."""
        if self.attempt_count >= self.max_retries:
            return False
        if not self.previous_scores:
            return True
        # Retry if latest score is below acceptable (40)
        return self.previous_scores[-1] < 40


class ToolCallResult(BaseModel):
    """Result from a tool call.

    Attributes:
        tool_name: Name of the tool called.
        success: Whether the call succeeded.
        result: The result data if successful.
        error: Error message if failed.
        execution_time_ms: Execution time in milliseconds.
    """

    tool_name: str = Field(..., description="Tool name")
    success: bool = Field(..., description="Whether call succeeded")
    result: Any | None = Field(default=None, description="Result data")
    error: str | None = Field(default=None, description="Error message")
    execution_time_ms: int = Field(default=0, ge=0, description="Execution time in ms")


class AgentStep(BaseModel):
    """A single step in agent execution.

    Attributes:
        step_number: Step sequence number.
        step_name: Human-readable step name.
        description: What this step does.
        tool_calls: Tool calls made in this step.
        reasoning: Agent's reasoning for this step.
        duration_ms: Step duration in milliseconds.
    """

    step_number: int = Field(..., ge=0, description="Step sequence number")
    step_name: str = Field(..., description="Step name")
    description: str = Field(..., description="Step description")
    tool_calls: list[ToolCallResult] = Field(default_factory=list, description="Tool calls made")
    reasoning: str | None = Field(default=None, description="Agent reasoning")
    duration_ms: int = Field(default=0, ge=0, description="Step duration")


class AgentExecutionTrace(BaseModel):
    """Complete execution trace for debugging.

    Attributes:
        session_id: Session identifier.
        request: Original request.
        steps: List of execution steps.
        total_duration_ms: Total execution time.
        final_score: Final feng shui score.
        success: Whether execution succeeded.
    """

    session_id: str = Field(..., description="Session ID")
    request: FengShuiLayoutRequest = Field(..., description="Original request")
    steps: list[AgentStep] = Field(default_factory=list, description="Execution steps")
    total_duration_ms: int = Field(default=0, ge=0, description="Total duration")
    final_score: int | None = Field(default=None, description="Final score")
    success: bool = Field(default=False, description="Overall success")
