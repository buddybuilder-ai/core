"""Agent context DTOs for feng shui layout generation."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from src.modules.layout.domain.entities import Room
from src.modules.layout.domain.value_objects import FengShuiScore


class AgentPhase(str, Enum):
    """Phases of the feng shui layout agent workflow."""

    INITIALIZATION = "initialization"
    INPUT_ANALYSIS = "input_analysis"
    SPATIAL_ANALYSIS = "spatial_analysis"
    RULE_RETRIEVAL = "rule_retrieval"
    FURNITURE_SELECTION = "furniture_selection"
    PLACEMENT_PLANNING = "placement_planning"
    PLACEMENT_EXECUTION = "placement_execution"
    COLLISION_RESOLUTION = "collision_resolution"
    SCORING = "scoring"
    VALIDATION = "validation"
    OUTPUT_GENERATION = "output_generation"
    COMPLETED = "completed"
    FAILED = "failed"


class PlacementStrategy(str, Enum):
    """Strategies for furniture placement."""

    COMMAND_POSITION = "command_position"  # Optimal feng shui position
    WALL_ALIGNED = "wall_aligned"  # Against a wall
    CENTER_ROOM = "center_room"  # In room center
    NEAR_WINDOW = "near_window"  # Near natural light
    AWAY_FROM_DOOR = "away_from_door"  # Privacy-focused
    GRID_BASED = "grid_based"  # Systematic grid placement


@dataclass
class UserPreferences:
    """User preferences collected during clarification.

    Attributes:
        budget_level: Budget preference (low, medium, high).
        style_preference: Furniture style preference.
        natural_light_priority: How important natural light is.
        privacy_priority: How important privacy is.
        accessibility_needs: Any accessibility requirements.
        existing_furniture: IDs of furniture to keep.
        custom_preferences: Additional custom preferences.
    """

    budget_level: str = "medium"
    style_preference: str = "modern"
    natural_light_priority: str = "somewhat_important"
    privacy_priority: str = "somewhat_important"
    accessibility_needs: list[str] = field(default_factory=list)
    existing_furniture: list[str] = field(default_factory=list)
    custom_preferences: dict[str, Any] = field(default_factory=dict)


@dataclass
class PlacedFurniture:
    """A furniture item that has been placed in the layout.

    Attributes:
        id: Unique identifier.
        furniture_id: Reference to furniture catalog ID.
        name: Display name.
        category: Furniture category.
        pos_x: X position in meters.
        pos_z: Z position in meters.
        width: Width in meters.
        depth: Depth in meters.
        height: Height in meters.
        rotation: Rotation in degrees (0, 90, 180, 270).
        is_essential: Whether this is essential furniture.
        placement_strategy: Strategy used for placement.
        feng_shui_notes: Notes about feng shui considerations.
    """

    id: str
    furniture_id: str
    name: str
    category: str
    pos_x: float
    pos_z: float
    width: float
    depth: float
    height: float
    rotation: int = 0
    is_essential: bool = False
    placement_strategy: PlacementStrategy = PlacementStrategy.GRID_BASED
    feng_shui_notes: list[str] = field(default_factory=list)

    @property
    def end_x(self) -> float:
        """Get the end X coordinate."""
        eff_width = self.depth if self.rotation in (90, 270) else self.width
        return self.pos_x + eff_width

    @property
    def end_z(self) -> float:
        """Get the end Z coordinate."""
        eff_depth = self.width if self.rotation in (90, 270) else self.depth
        return self.pos_z + eff_depth

    @property
    def center_x(self) -> float:
        """Get center X coordinate."""
        return (self.pos_x + self.end_x) / 2

    @property
    def center_z(self) -> float:
        """Get center Z coordinate."""
        return (self.pos_z + self.end_z) / 2

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON output."""
        return {
            "id": self.id,
            "furniture_id": self.furniture_id,
            "name": self.name,
            "category": self.category,
            "position": {"x": self.pos_x, "z": self.pos_z},
            "dimensions": {
                "width": self.width,
                "depth": self.depth,
                "height": self.height,
            },
            "rotation": self.rotation,
            "is_essential": self.is_essential,
            "placement_strategy": self.placement_strategy.value,
            "feng_shui_notes": self.feng_shui_notes,
        }


@dataclass
class AgentContext:
    """Context maintained throughout the feng shui layout agent workflow.

    This context is passed between agent phases and accumulates
    information as the layout is generated.

    Attributes:
        room: The room being designed.
        room_type: Type of room (bedroom, office, etc.).
        phase: Current agent phase.
        user_preferences: Collected user preferences.
        selected_furniture: Furniture selected for placement.
        placed_furniture: Furniture that has been placed.
        feng_shui_rules: Applicable feng shui rules.
        feng_shui_score: Current feng shui score.
        validation_errors: Any validation errors encountered.
        validation_warnings: Any validation warnings.
        retry_count: Number of retries attempted.
        max_retries: Maximum retries allowed.
        metadata: Additional metadata.
    """

    room: Room
    room_type: str
    phase: AgentPhase = AgentPhase.INITIALIZATION
    user_preferences: UserPreferences = field(default_factory=UserPreferences)
    selected_furniture: list[dict[str, Any]] = field(default_factory=list)
    placed_furniture: list[PlacedFurniture] = field(default_factory=list)
    feng_shui_rules: list[dict[str, Any]] = field(default_factory=list)
    feng_shui_score: FengShuiScore | None = None
    validation_errors: list[str] = field(default_factory=list)
    validation_warnings: list[str] = field(default_factory=list)
    retry_count: int = 0
    max_retries: int = 3
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_completed(self) -> bool:
        """Check if the agent has completed."""
        return self.phase in (AgentPhase.COMPLETED, AgentPhase.FAILED)

    @property
    def is_failed(self) -> bool:
        """Check if the agent has failed."""
        return self.phase == AgentPhase.FAILED

    @property
    def can_retry(self) -> bool:
        """Check if the agent can retry."""
        return self.retry_count < self.max_retries

    @property
    def essential_furniture_placed(self) -> bool:
        """Check if all essential furniture has been placed."""
        essential_categories = set()
        for item in self.selected_furniture:
            if item.get("is_essential", False):
                essential_categories.add(item.get("category"))

        placed_categories = {
            f.category for f in self.placed_furniture if f.is_essential
        }
        return essential_categories.issubset(placed_categories)

    def advance_phase(self, next_phase: AgentPhase) -> None:
        """Advance to the next phase."""
        self.phase = next_phase

    def add_error(self, error: str) -> None:
        """Add a validation error."""
        self.validation_errors.append(error)

    def add_warning(self, warning: str) -> None:
        """Add a validation warning."""
        self.validation_warnings.append(warning)

    def increment_retry(self) -> bool:
        """Increment retry count. Returns True if can still retry."""
        self.retry_count += 1
        return self.can_retry

    def get_placed_furniture_by_category(
        self, category: str
    ) -> list[PlacedFurniture]:
        """Get placed furniture by category."""
        return [f for f in self.placed_furniture if f.category == category]

    def get_furniture_positions(self) -> list[tuple[float, float, float, float]]:
        """Get all furniture positions as (x, z, width, depth) tuples."""
        positions = []
        for f in self.placed_furniture:
            eff_width = f.depth if f.rotation in (90, 270) else f.width
            eff_depth = f.width if f.rotation in (90, 270) else f.depth
            positions.append((f.pos_x, f.pos_z, eff_width, eff_depth))
        return positions


@dataclass
class AgentState:
    """Immutable snapshot of agent state for logging/debugging.

    Attributes:
        phase: Current phase.
        placed_count: Number of items placed.
        score: Current feng shui score.
        errors: Number of errors.
        warnings: Number of warnings.
        retry_count: Current retry count.
    """

    phase: AgentPhase
    placed_count: int
    score: float | None
    errors: int
    warnings: int
    retry_count: int

    @classmethod
    def from_context(cls, context: AgentContext) -> "AgentState":
        """Create state snapshot from context."""
        return cls(
            phase=context.phase,
            placed_count=len(context.placed_furniture),
            score=context.feng_shui_score.total if context.feng_shui_score else None,
            errors=len(context.validation_errors),
            warnings=len(context.validation_warnings),
            retry_count=context.retry_count,
        )
