"""Input analyzer service for parsing and validating layout requests."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from src.modules.layout.application.dtos import (
    AgentContext,
    UserPreferences,
)
from src.modules.layout.domain.entities import (
    DoorPosition,
    Room,
    RoomType,
    WallSide,
    WindowPosition,
)
from src.modules.layout.domain.exceptions import FengShuiAgentError


class ValidationSeverity(StrEnum):
    """Severity level for validation issues."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass(frozen=True)
class ValidationIssue:
    """A validation issue found during input analysis."""

    field: str
    message: str
    severity: ValidationSeverity
    suggestion: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "field": self.field,
            "message": self.message,
            "severity": self.severity.value,
            "suggestion": self.suggestion,
        }


@dataclass
class InputAnalysisResult:
    """Result of input analysis."""

    is_valid: bool
    room: Room | None = None
    room_type_str: str = ""
    doors: list[dict[str, Any]] = field(default_factory=list)
    windows: list[dict[str, Any]] = field(default_factory=list)
    preferences: UserPreferences = field(default_factory=UserPreferences)
    issues: list[ValidationIssue] = field(default_factory=list)
    raw_input: dict[str, Any] = field(default_factory=dict)

    @property
    def has_errors(self) -> bool:
        """Check if there are any error-level issues."""
        return any(issue.severity == ValidationSeverity.ERROR for issue in self.issues)

    @property
    def has_warnings(self) -> bool:
        """Check if there are any warning-level issues."""
        return any(issue.severity == ValidationSeverity.WARNING for issue in self.issues)

    @property
    def error_messages(self) -> list[str]:
        """Get all error messages."""
        return [
            issue.message for issue in self.issues if issue.severity == ValidationSeverity.ERROR
        ]

    @property
    def warning_messages(self) -> list[str]:
        """Get all warning messages."""
        return [
            issue.message for issue in self.issues if issue.severity == ValidationSeverity.WARNING
        ]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "is_valid": self.is_valid,
            "room_type": self.room_type_str,
            "has_errors": self.has_errors,
            "has_warnings": self.has_warnings,
            "issues": [issue.to_dict() for issue in self.issues],
        }


class InputAnalyzer:
    """Service for analyzing and validating layout input requests.

    This service is responsible for:
    - Parsing raw input dictionaries into structured data
    - Validating room dimensions and properties
    - Extracting door and window information
    - Converting room type strings to domain enums
    - Creating initial agent context
    """

    # Room dimension constraints (in meters)
    MIN_ROOM_WIDTH: float = 2.0
    MAX_ROOM_WIDTH: float = 20.0
    MIN_ROOM_DEPTH: float = 2.0
    MAX_ROOM_DEPTH: float = 20.0
    MIN_ROOM_HEIGHT: float = 2.2
    MAX_ROOM_HEIGHT: float = 5.0

    # Door constraints
    MIN_DOOR_WIDTH: float = 0.6
    MAX_DOOR_WIDTH: float = 2.0
    DEFAULT_DOOR_WIDTH: float = 0.9

    # Window constraints
    MIN_WINDOW_WIDTH: float = 0.3
    MAX_WINDOW_WIDTH: float = 5.0
    DEFAULT_WINDOW_HEIGHT: float = 1.2

    # Room type mapping
    ROOM_TYPE_MAPPING: dict[str, RoomType] = {
        "bedroom": RoomType.BEDROOM,
        "living_room": RoomType.LIVING_ROOM,
        "livingroom": RoomType.LIVING_ROOM,
        "living": RoomType.LIVING_ROOM,
        "office": RoomType.OFFICE,
        "study": RoomType.OFFICE,
        "home_office": RoomType.OFFICE,
        "dining_room": RoomType.DINING_ROOM,
        "diningroom": RoomType.DINING_ROOM,
        "dining": RoomType.DINING_ROOM,
        "studio_apartment": RoomType.STUDIO_APARTMENT,
        "studio": RoomType.STUDIO_APARTMENT,
    }

    # Valid wall sides
    VALID_WALLS: set[str] = {"north", "south", "east", "west"}

    def analyze(self, input_data: dict[str, Any]) -> InputAnalysisResult:
        """Analyze and validate input data.

        Args:
            input_data: Raw input dictionary from API request.

        Returns:
            InputAnalysisResult with validation status and parsed data.
        """
        issues: list[ValidationIssue] = []
        room: Room | None = None
        room_type_str = ""
        doors: list[dict[str, Any]] = []
        windows: list[dict[str, Any]] = []
        preferences = UserPreferences()

        # Validate and extract room type
        room_type_result = self._validate_room_type(input_data)
        issues.extend(room_type_result["issues"])
        room_type_str = room_type_result.get("room_type_str", "")
        room_type = room_type_result.get("room_type")

        # Validate and extract dimensions
        dims_result = self._validate_dimensions(input_data)
        issues.extend(dims_result["issues"])

        # Validate and extract doors
        doors_result = self._validate_doors(input_data, dims_result)
        issues.extend(doors_result["issues"])
        doors = doors_result.get("doors", [])

        # Validate and extract windows
        windows_result = self._validate_windows(input_data, dims_result)
        issues.extend(windows_result["issues"])
        windows = windows_result.get("windows", [])

        # Extract preferences
        preferences = self._extract_preferences(input_data)

        # Create Room entity if no errors
        has_errors = any(i.severity == ValidationSeverity.ERROR for i in issues)
        if not has_errors and room_type is not None:
            try:
                # Convert door dicts to DoorPosition objects
                door_positions = [
                    DoorPosition(
                        wall=self._parse_wall_side(door["wall"]),
                        offset=door["offset"],
                        width=door.get("width", self.DEFAULT_DOOR_WIDTH),
                    )
                    for door in doors
                ]

                # Convert window dicts to WindowPosition objects
                window_positions = [
                    WindowPosition(
                        wall=self._parse_wall_side(window["wall"]),
                        offset=window["offset"],
                        width=window["width"],
                        height=window.get("height", self.DEFAULT_WINDOW_HEIGHT),
                    )
                    for window in windows
                ]

                room = Room(
                    width=dims_result.get("width", 0),
                    depth=dims_result.get("depth", 0),
                    height=dims_result.get("height", 2.5),
                    room_type=room_type,
                    doors=door_positions,
                    windows=window_positions,
                )
            except FengShuiAgentError as e:
                issues.append(
                    ValidationIssue(
                        field="room",
                        message=str(e),
                        severity=ValidationSeverity.ERROR,
                    )
                )
                room = None

        return InputAnalysisResult(
            is_valid=not has_errors and room is not None,
            room=room,
            room_type_str=room_type_str,
            doors=doors,
            windows=windows,
            preferences=preferences,
            issues=issues,
            raw_input=input_data,
        )

    def create_context(self, analysis_result: InputAnalysisResult) -> AgentContext:
        """Create agent context from analysis result.

        Args:
            analysis_result: Validated input analysis result.

        Returns:
            Initialized AgentContext.

        Raises:
            ValueError: If analysis result is invalid.
        """
        if not analysis_result.is_valid or analysis_result.room is None:
            error_msgs = "; ".join(analysis_result.error_messages)
            msg = f"Cannot create context from invalid input: {error_msgs}"
            raise ValueError(msg)

        context = AgentContext(
            room=analysis_result.room,
            room_type=analysis_result.room_type_str,
            user_preferences=analysis_result.preferences,
        )

        # Add any warnings to context
        for warning in analysis_result.warning_messages:
            context.add_warning(warning)

        return context

    def _validate_room_type(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """Validate and extract room type.

        Args:
            input_data: Raw input dictionary.

        Returns:
            Dictionary with room_type, room_type_str, and issues.
        """
        issues: list[ValidationIssue] = []
        room_type: RoomType | None = None
        room_type_str = ""

        raw_type = input_data.get("room_type")
        if raw_type is None:
            issues.append(
                ValidationIssue(
                    field="room_type",
                    message="Room type is required",
                    severity=ValidationSeverity.ERROR,
                    suggestion="Specify one of: bedroom, living_room, office, dining_room",
                )
            )
        elif not isinstance(raw_type, str):
            issues.append(
                ValidationIssue(
                    field="room_type",
                    message=f"Room type must be a string, got {type(raw_type).__name__}",
                    severity=ValidationSeverity.ERROR,
                )
            )
        else:
            room_type_str = raw_type.lower().strip()
            room_type = self.ROOM_TYPE_MAPPING.get(room_type_str)
            if room_type is None:
                issues.append(
                    ValidationIssue(
                        field="room_type",
                        message=f"Unknown room type: {raw_type}",
                        severity=ValidationSeverity.ERROR,
                        suggestion=f"Valid types: {', '.join(self.ROOM_TYPE_MAPPING.keys())}",
                    )
                )

        return {
            "room_type": room_type,
            "room_type_str": room_type_str,
            "issues": issues,
        }

    def _validate_dimensions(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """Validate and extract room dimensions.

        Args:
            input_data: Raw input dictionary.

        Returns:
            Dictionary with width, depth, height, and issues.
        """
        issues: list[ValidationIssue] = []
        width = 0.0
        depth = 0.0
        height = 2.5  # Default ceiling height

        # Check for dimensions object
        dims = input_data.get("dimensions", {})
        if not dims:
            # Try flat structure
            dims = {
                "width": input_data.get("width"),
                "depth": input_data.get("depth"),
                "height": input_data.get("height"),
            }

        # Validate width
        raw_width = dims.get("width")
        if raw_width is None:
            issues.append(
                ValidationIssue(
                    field="dimensions.width",
                    message="Room width is required",
                    severity=ValidationSeverity.ERROR,
                )
            )
        else:
            try:
                width = float(raw_width)
                if width < self.MIN_ROOM_WIDTH:
                    issues.append(
                        ValidationIssue(
                            field="dimensions.width",
                            message=f"Room width {width}m is too small (min: {self.MIN_ROOM_WIDTH}m)",
                            severity=ValidationSeverity.ERROR,
                        )
                    )
                elif width > self.MAX_ROOM_WIDTH:
                    issues.append(
                        ValidationIssue(
                            field="dimensions.width",
                            message=f"Room width {width}m exceeds maximum ({self.MAX_ROOM_WIDTH}m)",
                            severity=ValidationSeverity.WARNING,
                            suggestion="Consider splitting into multiple rooms",
                        )
                    )
            except (TypeError, ValueError):
                issues.append(
                    ValidationIssue(
                        field="dimensions.width",
                        message=f"Invalid width value: {raw_width}",
                        severity=ValidationSeverity.ERROR,
                    )
                )

        # Validate depth
        raw_depth = dims.get("depth")
        if raw_depth is None:
            issues.append(
                ValidationIssue(
                    field="dimensions.depth",
                    message="Room depth is required",
                    severity=ValidationSeverity.ERROR,
                )
            )
        else:
            try:
                depth = float(raw_depth)
                if depth < self.MIN_ROOM_DEPTH:
                    issues.append(
                        ValidationIssue(
                            field="dimensions.depth",
                            message=f"Room depth {depth}m is too small (min: {self.MIN_ROOM_DEPTH}m)",
                            severity=ValidationSeverity.ERROR,
                        )
                    )
                elif depth > self.MAX_ROOM_DEPTH:
                    issues.append(
                        ValidationIssue(
                            field="dimensions.depth",
                            message=f"Room depth {depth}m exceeds maximum ({self.MAX_ROOM_DEPTH}m)",
                            severity=ValidationSeverity.WARNING,
                        )
                    )
            except (TypeError, ValueError):
                issues.append(
                    ValidationIssue(
                        field="dimensions.depth",
                        message=f"Invalid depth value: {raw_depth}",
                        severity=ValidationSeverity.ERROR,
                    )
                )

        # Validate height (optional)
        raw_height = dims.get("height")
        if raw_height is not None:
            try:
                height = float(raw_height)
                if height < self.MIN_ROOM_HEIGHT:
                    issues.append(
                        ValidationIssue(
                            field="dimensions.height",
                            message=f"Room height {height}m is below minimum ({self.MIN_ROOM_HEIGHT}m)",
                            severity=ValidationSeverity.WARNING,
                        )
                    )
                elif height > self.MAX_ROOM_HEIGHT:
                    issues.append(
                        ValidationIssue(
                            field="dimensions.height",
                            message=f"Room height {height}m is unusually tall",
                            severity=ValidationSeverity.INFO,
                        )
                    )
            except (TypeError, ValueError):
                issues.append(
                    ValidationIssue(
                        field="dimensions.height",
                        message=f"Invalid height value: {raw_height}",
                        severity=ValidationSeverity.WARNING,
                        suggestion="Using default height of 2.5m",
                    )
                )
                height = 2.5

        # Check aspect ratio
        if width > 0 and depth > 0:
            aspect_ratio = max(width, depth) / min(width, depth)
            if aspect_ratio > 4:
                issues.append(
                    ValidationIssue(
                        field="dimensions",
                        message=f"Room aspect ratio ({aspect_ratio:.1f}:1) is very elongated",
                        severity=ValidationSeverity.WARNING,
                        suggestion="Consider feng shui zoning for long narrow rooms",
                    )
                )

        return {
            "width": width,
            "depth": depth,
            "height": height,
            "issues": issues,
        }

    def _validate_doors(
        self, input_data: dict[str, Any], dims_result: dict[str, Any]
    ) -> dict[str, Any]:
        """Validate and extract door information.

        Args:
            input_data: Raw input dictionary.
            dims_result: Validated dimensions result.

        Returns:
            Dictionary with doors list and issues.
        """
        issues: list[ValidationIssue] = []
        doors: list[dict[str, Any]] = []

        raw_doors = input_data.get("doors", [])
        if not raw_doors:
            issues.append(
                ValidationIssue(
                    field="doors",
                    message="No doors specified",
                    severity=ValidationSeverity.WARNING,
                    suggestion="Specify at least one door for proper feng shui analysis",
                )
            )
            return {"doors": doors, "issues": issues}

        if not isinstance(raw_doors, list):
            issues.append(
                ValidationIssue(
                    field="doors",
                    message="Doors must be a list",
                    severity=ValidationSeverity.ERROR,
                )
            )
            return {"doors": doors, "issues": issues}

        width = dims_result.get("width", 0)
        depth = dims_result.get("depth", 0)

        for idx, door in enumerate(raw_doors):
            door_issues, valid_door = self._validate_single_door(door, idx, width, depth)
            issues.extend(door_issues)
            if valid_door:
                doors.append(valid_door)

        return {"doors": doors, "issues": issues}

    def _validate_single_door(
        self,
        door: Any,
        idx: int,
        room_width: float,
        room_depth: float,
    ) -> tuple[list[ValidationIssue], dict[str, Any] | None]:
        """Validate a single door entry.

        Args:
            door: Door data to validate.
            idx: Index in doors list.
            room_width: Room width for offset validation.
            room_depth: Room depth for offset validation.

        Returns:
            Tuple of (issues, validated_door or None).
        """
        issues: list[ValidationIssue] = []
        field_prefix = f"doors[{idx}]"

        if not isinstance(door, dict):
            issues.append(
                ValidationIssue(
                    field=field_prefix,
                    message="Door entry must be an object",
                    severity=ValidationSeverity.ERROR,
                )
            )
            return issues, None

        # Validate wall
        wall = door.get("wall", "").lower().strip()
        if not wall:
            issues.append(
                ValidationIssue(
                    field=f"{field_prefix}.wall",
                    message="Door wall is required",
                    severity=ValidationSeverity.ERROR,
                )
            )
            return issues, None

        if wall not in self.VALID_WALLS:
            issues.append(
                ValidationIssue(
                    field=f"{field_prefix}.wall",
                    message=f"Invalid wall: {wall}",
                    severity=ValidationSeverity.ERROR,
                    suggestion=f"Valid walls: {', '.join(self.VALID_WALLS)}",
                )
            )
            return issues, None

        # Validate offset
        raw_offset = door.get("offset", 0)
        try:
            offset = float(raw_offset)
        except (TypeError, ValueError):
            issues.append(
                ValidationIssue(
                    field=f"{field_prefix}.offset",
                    message=f"Invalid offset value: {raw_offset}",
                    severity=ValidationSeverity.ERROR,
                )
            )
            return issues, None

        # Get max offset based on wall
        max_offset = room_width if wall in ("north", "south") else room_depth
        door_width = door.get("width", self.DEFAULT_DOOR_WIDTH)

        try:
            door_width = float(door_width)
        except (TypeError, ValueError):
            door_width = self.DEFAULT_DOOR_WIDTH

        if offset < 0:
            issues.append(
                ValidationIssue(
                    field=f"{field_prefix}.offset",
                    message="Door offset cannot be negative",
                    severity=ValidationSeverity.ERROR,
                )
            )
            return issues, None

        if max_offset > 0 and offset + door_width > max_offset:
            issues.append(
                ValidationIssue(
                    field=f"{field_prefix}.offset",
                    message=f"Door extends beyond wall (offset {offset} + width {door_width} > {max_offset})",
                    severity=ValidationSeverity.WARNING,
                )
            )

        # Validate door width
        if door_width < self.MIN_DOOR_WIDTH:
            issues.append(
                ValidationIssue(
                    field=f"{field_prefix}.width",
                    message=f"Door width {door_width}m is too narrow",
                    severity=ValidationSeverity.WARNING,
                )
            )
        elif door_width > self.MAX_DOOR_WIDTH:
            issues.append(
                ValidationIssue(
                    field=f"{field_prefix}.width",
                    message=f"Door width {door_width}m is unusually wide",
                    severity=ValidationSeverity.INFO,
                )
            )

        return issues, {
            "wall": wall,
            "offset": offset,
            "width": door_width,
        }

    def _validate_windows(
        self, input_data: dict[str, Any], dims_result: dict[str, Any]
    ) -> dict[str, Any]:
        """Validate and extract window information.

        Args:
            input_data: Raw input dictionary.
            dims_result: Validated dimensions result.

        Returns:
            Dictionary with windows list and issues.
        """
        issues: list[ValidationIssue] = []
        windows: list[dict[str, Any]] = []

        raw_windows = input_data.get("windows", [])
        if not raw_windows:
            issues.append(
                ValidationIssue(
                    field="windows",
                    message="No windows specified",
                    severity=ValidationSeverity.INFO,
                    suggestion="Windows affect natural light and chi flow",
                )
            )
            return {"windows": windows, "issues": issues}

        if not isinstance(raw_windows, list):
            issues.append(
                ValidationIssue(
                    field="windows",
                    message="Windows must be a list",
                    severity=ValidationSeverity.ERROR,
                )
            )
            return {"windows": windows, "issues": issues}

        width = dims_result.get("width", 0)
        depth = dims_result.get("depth", 0)

        for idx, window in enumerate(raw_windows):
            window_issues, valid_window = self._validate_single_window(window, idx, width, depth)
            issues.extend(window_issues)
            if valid_window:
                windows.append(valid_window)

        return {"windows": windows, "issues": issues}

    def _validate_single_window(
        self,
        window: Any,
        idx: int,
        room_width: float,
        room_depth: float,
    ) -> tuple[list[ValidationIssue], dict[str, Any] | None]:
        """Validate a single window entry.

        Args:
            window: Window data to validate.
            idx: Index in windows list.
            room_width: Room width for offset validation.
            room_depth: Room depth for offset validation.

        Returns:
            Tuple of (issues, validated_window or None).
        """
        issues: list[ValidationIssue] = []
        field_prefix = f"windows[{idx}]"

        if not isinstance(window, dict):
            issues.append(
                ValidationIssue(
                    field=field_prefix,
                    message="Window entry must be an object",
                    severity=ValidationSeverity.ERROR,
                )
            )
            return issues, None

        # Validate wall
        wall = window.get("wall", "").lower().strip()
        if not wall:
            issues.append(
                ValidationIssue(
                    field=f"{field_prefix}.wall",
                    message="Window wall is required",
                    severity=ValidationSeverity.ERROR,
                )
            )
            return issues, None

        if wall not in self.VALID_WALLS:
            issues.append(
                ValidationIssue(
                    field=f"{field_prefix}.wall",
                    message=f"Invalid wall: {wall}",
                    severity=ValidationSeverity.ERROR,
                    suggestion=f"Valid walls: {', '.join(self.VALID_WALLS)}",
                )
            )
            return issues, None

        # Validate offset
        raw_offset = window.get("offset", 0)
        try:
            offset = float(raw_offset)
        except (TypeError, ValueError):
            issues.append(
                ValidationIssue(
                    field=f"{field_prefix}.offset",
                    message=f"Invalid offset value: {raw_offset}",
                    severity=ValidationSeverity.ERROR,
                )
            )
            return issues, None

        # Validate width
        raw_width = window.get("width", 1.0)
        try:
            win_width = float(raw_width)
        except (TypeError, ValueError):
            issues.append(
                ValidationIssue(
                    field=f"{field_prefix}.width",
                    message=f"Invalid width value: {raw_width}",
                    severity=ValidationSeverity.ERROR,
                )
            )
            return issues, None

        # Validate height (optional)
        raw_height = window.get("height", self.DEFAULT_WINDOW_HEIGHT)
        try:
            win_height = float(raw_height)
        except (TypeError, ValueError):
            win_height = self.DEFAULT_WINDOW_HEIGHT

        # Get max offset based on wall
        max_offset = room_width if wall in ("north", "south") else room_depth

        if offset < 0:
            issues.append(
                ValidationIssue(
                    field=f"{field_prefix}.offset",
                    message="Window offset cannot be negative",
                    severity=ValidationSeverity.ERROR,
                )
            )
            return issues, None

        if max_offset > 0 and offset + win_width > max_offset:
            issues.append(
                ValidationIssue(
                    field=f"{field_prefix}.offset",
                    message="Window extends beyond wall",
                    severity=ValidationSeverity.WARNING,
                )
            )

        if win_width < self.MIN_WINDOW_WIDTH:
            issues.append(
                ValidationIssue(
                    field=f"{field_prefix}.width",
                    message=f"Window width {win_width}m is very small",
                    severity=ValidationSeverity.INFO,
                )
            )
        elif win_width > self.MAX_WINDOW_WIDTH:
            issues.append(
                ValidationIssue(
                    field=f"{field_prefix}.width",
                    message=f"Window width {win_width}m is very large",
                    severity=ValidationSeverity.INFO,
                )
            )

        return issues, {
            "wall": wall,
            "offset": offset,
            "width": win_width,
            "height": win_height,
        }

    def _extract_preferences(self, input_data: dict[str, Any]) -> UserPreferences:
        """Extract user preferences from input.

        Args:
            input_data: Raw input dictionary.

        Returns:
            UserPreferences with extracted or default values.
        """
        prefs_data = input_data.get("preferences", {})
        if not isinstance(prefs_data, dict):
            prefs_data = {}

        return UserPreferences(
            budget_level=prefs_data.get("budget_level", "medium"),
            style_preference=prefs_data.get("style_preference", "modern"),
            natural_light_priority=prefs_data.get("natural_light_priority", "somewhat_important"),
            privacy_priority=prefs_data.get("privacy_priority", "somewhat_important"),
            accessibility_needs=prefs_data.get("accessibility_needs", []),
            existing_furniture=prefs_data.get("existing_furniture", []),
            custom_preferences=prefs_data.get("custom_preferences", {}),
        )

    def _parse_wall_side(self, wall: str) -> WallSide:
        """Parse wall string to WallSide enum.

        Args:
            wall: Wall name string (north, south, east, west).

        Returns:
            WallSide enum value.
        """
        wall_mapping = {
            "north": WallSide.NORTH,
            "south": WallSide.SOUTH,
            "east": WallSide.EAST,
            "west": WallSide.WEST,
        }
        return wall_mapping[wall.lower()]
