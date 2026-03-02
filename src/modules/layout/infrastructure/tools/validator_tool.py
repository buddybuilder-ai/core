"""Validator tool for feng shui layout agent."""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from src.modules.layout.infrastructure.tools.base import BaseTool, ToolResult


class ValidationLevel(StrEnum):
    """Validation severity levels."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass(frozen=True)
class ValidationIssue:
    """A validation issue found in the layout.

    Attributes:
        code: Issue code for programmatic handling.
        level: Severity level.
        message: Human-readable message.
        item_field: Field or item that caused the issue.
        details: Additional details about the issue.
    """

    code: str
    level: ValidationLevel
    message: str
    item_field: str = ""
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "code": self.code,
            "level": self.level.value,
            "message": self.message,
            "field": self.item_field,
            "details": self.details,
        }


@dataclass
class LayoutItem:
    """A furniture item in the layout for validation.

    Attributes:
        id: Unique identifier.
        name: Display name.
        category: Furniture category.
        pos_x: X position in meters.
        pos_z: Z position in meters.
        width: Width in meters.
        depth: Depth in meters.
        rotation: Rotation in degrees (0, 90, 180, 270).
        is_essential: Whether this is essential furniture.
    """

    id: str
    name: str
    category: str
    pos_x: float
    pos_z: float
    width: float
    depth: float
    rotation: int = 0
    is_essential: bool = False


@dataclass
class ValidatorInput:
    """Input for layout validation.

    Attributes:
        room_width: Room width in meters.
        room_depth: Room depth in meters.
        room_type: Type of room (bedroom, office, etc.).
        items: List of placed furniture items.
        feng_shui_score: Calculated feng shui score.
        strict_mode: If True, warnings are treated as errors.
    """

    room_width: float
    room_depth: float
    room_type: str
    items: list[LayoutItem] = field(default_factory=list)
    feng_shui_score: float = 0.0
    strict_mode: bool = False


@dataclass(frozen=True)
class ValidatorOutput:
    """Output of layout validation.

    Attributes:
        is_valid: Whether the layout passes validation.
        issues: List of validation issues found.
        error_count: Number of error-level issues.
        warning_count: Number of warning-level issues.
        info_count: Number of info-level issues.
    """

    is_valid: bool
    issues: list[ValidationIssue]
    error_count: int
    warning_count: int
    info_count: int

    def get_issues_by_level(self, level: ValidationLevel) -> list[ValidationIssue]:
        """Get issues of a specific level."""
        return [i for i in self.issues if i.level == level]

    def get_issues_for_item(self, item_id: str) -> list[ValidationIssue]:
        """Get issues related to a specific item."""
        return [i for i in self.issues if i.item_field == item_id]


class ValidatorTool(BaseTool[ValidatorInput, ValidatorOutput]):
    """Tool for validating feng shui layouts.

    This tool validates:
    - Room dimensions are valid
    - All items are within room bounds
    - Essential furniture is present
    - Feng shui score meets minimum threshold
    - Items have valid positions and rotations
    - JSON structure is correct
    """

    # Minimum acceptable feng shui score
    MIN_FENG_SHUI_SCORE = 40

    # Essential furniture by room type
    ESSENTIAL_FURNITURE = {
        "bedroom": ["bed"],
        "living_room": ["sofa"],
        "office": ["desk", "chair"],
        "dining_room": ["dining_table"],
    }

    @property
    def name(self) -> str:
        return "VALIDATOR"

    @property
    def description(self) -> str:
        return (
            "Validates feng shui layout for correctness including item positions, "
            "room bounds, essential furniture, and feng shui score requirements."
        )

    def validate_input(self, input_data: ValidatorInput) -> list[str]:
        """Validate the validator input."""
        errors = []
        if input_data.room_width <= 0:
            errors.append("Room width must be positive")
        if input_data.room_depth <= 0:
            errors.append("Room depth must be positive")
        valid_room_types = {"bedroom", "living_room", "office", "dining_room"}
        if input_data.room_type not in valid_room_types:
            errors.append(f"Invalid room_type. Must be one of: {valid_room_types}")
        return errors

    async def execute(self, input_data: ValidatorInput) -> ToolResult[ValidatorOutput]:
        """Execute layout validation."""
        import time

        start_time = time.perf_counter()

        issues: list[ValidationIssue] = []

        # Validate room dimensions
        room_issues = self._validate_room_dimensions(input_data)
        issues.extend(room_issues)

        # Validate item positions
        position_issues = self._validate_item_positions(input_data)
        issues.extend(position_issues)

        # Validate essential furniture
        essential_issues = self._validate_essential_furniture(input_data)
        issues.extend(essential_issues)

        # Validate feng shui score
        score_issues = self._validate_feng_shui_score(input_data)
        issues.extend(score_issues)

        # Validate item rotations
        rotation_issues = self._validate_rotations(input_data)
        issues.extend(rotation_issues)

        # Validate item overlaps (basic check)
        overlap_issues = self._validate_no_overlaps(input_data)
        issues.extend(overlap_issues)

        # Count by level
        error_count = sum(1 for i in issues if i.level == ValidationLevel.ERROR)
        warning_count = sum(1 for i in issues if i.level == ValidationLevel.WARNING)
        info_count = sum(1 for i in issues if i.level == ValidationLevel.INFO)

        # Determine if valid
        if input_data.strict_mode:
            is_valid = error_count == 0 and warning_count == 0
        else:
            is_valid = error_count == 0

        elapsed_ms = (time.perf_counter() - start_time) * 1000

        output = ValidatorOutput(
            is_valid=is_valid,
            issues=issues,
            error_count=error_count,
            warning_count=warning_count,
            info_count=info_count,
        )

        return ToolResult.ok(
            data=output,
            execution_time_ms=elapsed_ms,
            metadata={
                "items_validated": len(input_data.items),
                "is_valid": is_valid,
                "error_count": error_count,
                "warning_count": warning_count,
                "strict_mode": input_data.strict_mode,
            },
        )

    def _validate_room_dimensions(self, input_data: ValidatorInput) -> list[ValidationIssue]:
        """Validate room dimensions are reasonable."""
        issues = []

        # Minimum room size
        min_size = 2.0  # 2m minimum
        if input_data.room_width < min_size:
            issues.append(
                ValidationIssue(
                    code="ROOM_TOO_NARROW",
                    level=ValidationLevel.WARNING,
                    message=f"Room width {input_data.room_width}m is quite narrow (min recommended: {min_size}m)",
                    item_field="room_width",
                )
            )
        if input_data.room_depth < min_size:
            issues.append(
                ValidationIssue(
                    code="ROOM_TOO_SHALLOW",
                    level=ValidationLevel.WARNING,
                    message=f"Room depth {input_data.room_depth}m is quite shallow (min recommended: {min_size}m)",
                    item_field="room_depth",
                )
            )

        # Maximum room size
        max_size = 20.0  # 20m maximum
        if input_data.room_width > max_size or input_data.room_depth > max_size:
            issues.append(
                ValidationIssue(
                    code="ROOM_TOO_LARGE",
                    level=ValidationLevel.INFO,
                    message="Room is quite large - consider zoning the space",
                    item_field="room_dimensions",
                )
            )

        return issues

    def _validate_item_positions(self, input_data: ValidatorInput) -> list[ValidationIssue]:
        """Validate that all items are within room bounds."""
        issues = []

        for item in input_data.items:
            # Get effective dimensions based on rotation
            if item.rotation in (90, 270):
                eff_width, eff_depth = item.depth, item.width
            else:
                eff_width, eff_depth = item.width, item.depth

            # Check bounds
            if item.pos_x < 0:
                issues.append(
                    ValidationIssue(
                        code="ITEM_OUT_OF_BOUNDS",
                        level=ValidationLevel.ERROR,
                        message=f"'{item.name}' has negative X position ({item.pos_x}m)",
                        item_field=item.id,
                        details={"pos_x": item.pos_x},
                    )
                )
            if item.pos_z < 0:
                issues.append(
                    ValidationIssue(
                        code="ITEM_OUT_OF_BOUNDS",
                        level=ValidationLevel.ERROR,
                        message=f"'{item.name}' has negative Z position ({item.pos_z}m)",
                        item_field=item.id,
                        details={"pos_z": item.pos_z},
                    )
                )
            if item.pos_x + eff_width > input_data.room_width:
                issues.append(
                    ValidationIssue(
                        code="ITEM_OUT_OF_BOUNDS",
                        level=ValidationLevel.ERROR,
                        message=f"'{item.name}' extends beyond room width",
                        item_field=item.id,
                        details={
                            "item_end_x": item.pos_x + eff_width,
                            "room_width": input_data.room_width,
                        },
                    )
                )
            if item.pos_z + eff_depth > input_data.room_depth:
                issues.append(
                    ValidationIssue(
                        code="ITEM_OUT_OF_BOUNDS",
                        level=ValidationLevel.ERROR,
                        message=f"'{item.name}' extends beyond room depth",
                        item_field=item.id,
                        details={
                            "item_end_z": item.pos_z + eff_depth,
                            "room_depth": input_data.room_depth,
                        },
                    )
                )

        return issues

    def _validate_essential_furniture(self, input_data: ValidatorInput) -> list[ValidationIssue]:
        """Validate that essential furniture is present."""
        issues = []

        required = self.ESSENTIAL_FURNITURE.get(input_data.room_type, [])
        present_categories = {item.category for item in input_data.items}

        for required_category in required:
            if required_category not in present_categories:
                issues.append(
                    ValidationIssue(
                        code="MISSING_ESSENTIAL",
                        level=ValidationLevel.ERROR,
                        message=f"Essential furniture missing: {required_category}",
                        item_field="items",
                        details={"missing_category": required_category},
                    )
                )

        return issues

    def _validate_feng_shui_score(self, input_data: ValidatorInput) -> list[ValidationIssue]:
        """Validate feng shui score meets minimum."""
        issues = []

        if input_data.feng_shui_score < self.MIN_FENG_SHUI_SCORE:
            issues.append(
                ValidationIssue(
                    code="LOW_FENG_SHUI_SCORE",
                    level=ValidationLevel.WARNING,
                    message=(
                        f"Feng shui score {input_data.feng_shui_score} is below minimum "
                        f"threshold ({self.MIN_FENG_SHUI_SCORE})"
                    ),
                    item_field="feng_shui_score",
                    details={
                        "score": input_data.feng_shui_score,
                        "minimum": self.MIN_FENG_SHUI_SCORE,
                    },
                )
            )

        if input_data.feng_shui_score >= 80:
            issues.append(
                ValidationIssue(
                    code="EXCELLENT_FENG_SHUI",
                    level=ValidationLevel.INFO,
                    message=f"Excellent feng shui score: {input_data.feng_shui_score}",
                    item_field="feng_shui_score",
                )
            )

        return issues

    def _validate_rotations(self, input_data: ValidatorInput) -> list[ValidationIssue]:
        """Validate item rotations are valid values."""
        issues = []
        valid_rotations = {0, 90, 180, 270}

        for item in input_data.items:
            if item.rotation not in valid_rotations:
                issues.append(
                    ValidationIssue(
                        code="INVALID_ROTATION",
                        level=ValidationLevel.ERROR,
                        message=f"'{item.name}' has invalid rotation {item.rotation} (must be 0, 90, 180, or 270)",
                        item_field=item.id,
                        details={"rotation": item.rotation},
                    )
                )

        return issues

    def _validate_no_overlaps(self, input_data: ValidatorInput) -> list[ValidationIssue]:
        """Basic check for overlapping items."""
        issues = []
        items = input_data.items

        for i, item1 in enumerate(items):
            for item2 in items[i + 1 :]:
                if self._items_overlap(item1, item2):
                    issues.append(
                        ValidationIssue(
                            code="ITEMS_OVERLAP",
                            level=ValidationLevel.ERROR,
                            message=f"'{item1.name}' overlaps with '{item2.name}'",
                            item_field=item1.id,
                            details={"overlaps_with": item2.id},
                        )
                    )

        return issues

    def _items_overlap(self, item1: LayoutItem, item2: LayoutItem) -> bool:
        """Check if two items overlap."""
        # Get effective dimensions based on rotation
        if item1.rotation in (90, 270):
            w1, d1 = item1.depth, item1.width
        else:
            w1, d1 = item1.width, item1.depth

        if item2.rotation in (90, 270):
            w2, d2 = item2.depth, item2.width
        else:
            w2, d2 = item2.width, item2.depth

        # Check AABB overlap
        return (
            item1.pos_x < item2.pos_x + w2
            and item1.pos_x + w1 > item2.pos_x
            and item1.pos_z < item2.pos_z + d2
            and item1.pos_z + d1 > item2.pos_z
        )

    def to_langchain_tool_schema(self) -> dict[str, Any]:
        """Convert to LangChain tool schema."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "room_width": {
                        "type": "number",
                        "description": "Room width in meters",
                    },
                    "room_depth": {
                        "type": "number",
                        "description": "Room depth in meters",
                    },
                    "room_type": {
                        "type": "string",
                        "enum": ["bedroom", "living_room", "office", "dining_room"],
                        "description": "Type of room",
                    },
                    "items": {
                        "type": "array",
                        "description": "List of furniture items with positions",
                    },
                    "feng_shui_score": {
                        "type": "number",
                        "description": "Calculated feng shui score (0-100)",
                    },
                },
                "required": ["room_width", "room_depth", "room_type", "items"],
            },
        }
