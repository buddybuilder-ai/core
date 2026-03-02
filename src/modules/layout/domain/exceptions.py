"""Domain exceptions for feng shui layout module."""

from __future__ import annotations

from typing import Any


class FengShuiAgentError(Exception):
    """Base exception for feng shui agent.

    All domain-specific exceptions inherit from this base class
    to allow catching all agent-related errors.
    """

    def __init__(
        self,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Initialize exception.

        Args:
            message: Human-readable error message.
            details: Optional additional details for debugging.
        """
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def __str__(self) -> str:
        """Return string representation."""
        if self.details:
            return f"{self.message} (details: {self.details})"
        return self.message


# ============================================================================
# Validation Errors
# ============================================================================


class ValidationError(FengShuiAgentError):
    """Base validation error."""

    pass


class InvalidRoomDimensionsError(ValidationError):
    """Room dimensions are invalid.

    Raised when room width, depth, or height is <= 0 or unrealistic.
    """

    def __init__(
        self,
        dimension: str,
        value: float,
        reason: str = "must be positive",
    ) -> None:
        """Initialize exception.

        Args:
            dimension: Which dimension is invalid (width/depth/height).
            value: The invalid value.
            reason: Why it's invalid.
        """
        super().__init__(
            f"Invalid room {dimension}: {value} ({reason})",
            details={"dimension": dimension, "value": value, "reason": reason},
        )
        self.dimension = dimension
        self.value = value


class InvalidDoorPositionError(ValidationError):
    """Door position is outside room bounds.

    Raised when a door is placed outside the room dimensions
    or overlaps with another door/window.
    """

    def __init__(
        self,
        wall: str,
        offset: float,
        room_dimension: float,
    ) -> None:
        """Initialize exception.

        Args:
            wall: Wall where door is placed.
            offset: Door offset from wall start.
            room_dimension: The relevant room dimension.
        """
        super().__init__(
            f"Door on {wall} wall at offset {offset} exceeds room dimension {room_dimension}",
            details={
                "wall": wall,
                "offset": offset,
                "room_dimension": room_dimension,
            },
        )


class InvalidWindowPositionError(ValidationError):
    """Window position is outside room bounds.

    Raised when a window is placed outside the room dimensions.
    """

    def __init__(
        self,
        wall: str,
        offset: float,
        room_dimension: float,
    ) -> None:
        """Initialize exception.

        Args:
            wall: Wall where window is placed.
            offset: Window offset from wall start.
            room_dimension: The relevant room dimension.
        """
        super().__init__(
            f"Window on {wall} wall at offset {offset} exceeds room dimension {room_dimension}",
            details={
                "wall": wall,
                "offset": offset,
                "room_dimension": room_dimension,
            },
        )


# ============================================================================
# Placement Errors
# ============================================================================


class PlacementError(FengShuiAgentError):
    """Base placement error."""

    pass


class NoValidPlacementError(PlacementError):
    """Cannot find valid placement for furniture.

    Raised when all placement strategies have been exhausted
    without finding a valid position.
    """

    def __init__(
        self,
        furniture_id: str,
        furniture_name: str,
        reason: str,
        attempts: int = 0,
    ) -> None:
        """Initialize exception.

        Args:
            furniture_id: ID of furniture that couldn't be placed.
            furniture_name: Name of furniture.
            reason: Why placement failed.
            attempts: Number of placement attempts made.
        """
        super().__init__(
            f"No valid placement for '{furniture_name}' ({furniture_id}): {reason}",
            details={
                "furniture_id": furniture_id,
                "furniture_name": furniture_name,
                "reason": reason,
                "attempts": attempts,
            },
        )
        self.furniture_id = furniture_id
        self.furniture_name = furniture_name


class InsufficientSpaceError(PlacementError):
    """Room too small for essential furniture.

    Raised when the room cannot accommodate required furniture
    even with the most compact arrangement.
    """

    def __init__(
        self,
        room_area: float,
        required_area: float,
        furniture_list: list[str],
    ) -> None:
        """Initialize exception.

        Args:
            room_area: Available room floor area in sq meters.
            required_area: Minimum required area for furniture.
            furniture_list: List of furniture that won't fit.
        """
        super().__init__(
            f"Insufficient space: room has {room_area:.1f}m² but requires {required_area:.1f}m²",
            details={
                "room_area": room_area,
                "required_area": required_area,
                "furniture_list": furniture_list,
            },
        )


class CollisionError(PlacementError):
    """Furniture placement causes collision.

    Raised when a placement would cause overlap with
    existing furniture or room elements.
    """

    def __init__(
        self,
        furniture_id: str,
        collides_with: str,
        collision_type: str = "furniture",
    ) -> None:
        """Initialize exception.

        Args:
            furniture_id: ID of furniture being placed.
            collides_with: What it collides with (furniture ID or element).
            collision_type: Type of collision (furniture/wall/door/window).
        """
        super().__init__(
            f"Collision: '{furniture_id}' collides with {collision_type} '{collides_with}'",
            details={
                "furniture_id": furniture_id,
                "collides_with": collides_with,
                "collision_type": collision_type,
            },
        )


class ClearanceViolationError(PlacementError):
    """Minimum clearance requirement violated.

    Raised when placement doesn't maintain required clearance
    for walkways or furniture access.
    """

    def __init__(
        self,
        location: str,
        actual_clearance: float,
        required_clearance: float,
    ) -> None:
        """Initialize exception.

        Args:
            location: Where the violation occurs.
            actual_clearance: Actual clearance in meters.
            required_clearance: Required clearance in meters.
        """
        super().__init__(
            f"Clearance violation at {location}: {actual_clearance:.2f}m < {required_clearance:.2f}m required",
            details={
                "location": location,
                "actual_clearance": actual_clearance,
                "required_clearance": required_clearance,
            },
        )


# ============================================================================
# Tool Errors
# ============================================================================


class ToolError(FengShuiAgentError):
    """Base tool execution error."""

    pass


class ToolInputError(ToolError):
    """Invalid input for tool.

    Raised when tool receives invalid or incomplete input.
    """

    def __init__(
        self,
        tool_name: str,
        field: str,
        reason: str,
    ) -> None:
        """Initialize exception.

        Args:
            tool_name: Name of the tool.
            field: Input field that's invalid.
            reason: Why it's invalid.
        """
        super().__init__(
            f"Invalid input for {tool_name}: {field} - {reason}",
            details={"tool_name": tool_name, "field": field, "reason": reason},
        )


class ToolExecutionError(ToolError):
    """Tool execution failed.

    Raised when a tool fails during execution.
    """

    def __init__(
        self,
        tool_name: str,
        reason: str,
        original_error: Exception | None = None,
    ) -> None:
        """Initialize exception.

        Args:
            tool_name: Name of the tool.
            reason: Why execution failed.
            original_error: The underlying exception if any.
        """
        super().__init__(
            f"Tool '{tool_name}' execution failed: {reason}",
            details={"tool_name": tool_name, "reason": reason},
        )
        self.original_error = original_error


class ToolTimeoutError(ToolError):
    """Tool execution timed out.

    Raised when a tool takes too long to execute.
    """

    def __init__(
        self,
        tool_name: str,
        timeout_seconds: float,
    ) -> None:
        """Initialize exception.

        Args:
            tool_name: Name of the tool.
            timeout_seconds: How long before timeout.
        """
        super().__init__(
            f"Tool '{tool_name}' timed out after {timeout_seconds}s",
            details={"tool_name": tool_name, "timeout_seconds": timeout_seconds},
        )


class RagSearchError(ToolError):
    """RAG search failed.

    Raised when feng shui knowledge retrieval fails.
    """

    def __init__(
        self,
        query: str,
        reason: str,
    ) -> None:
        """Initialize exception.

        Args:
            query: The search query that failed.
            reason: Why the search failed.
        """
        super().__init__(
            f"RAG search failed for '{query}': {reason}",
            details={"query": query, "reason": reason},
        )


class FurnitureDbError(ToolError):
    """Furniture database query failed.

    Raised when furniture catalog lookup fails.
    """

    def __init__(
        self,
        query_params: dict[str, Any],
        reason: str,
    ) -> None:
        """Initialize exception.

        Args:
            query_params: Parameters used in the query.
            reason: Why the query failed.
        """
        super().__init__(
            f"Furniture database query failed: {reason}",
            details={"query_params": query_params, "reason": reason},
        )


# ============================================================================
# Scoring Errors
# ============================================================================


class ScoringError(FengShuiAgentError):
    """Error during feng shui scoring."""

    def __init__(
        self,
        component: str,
        reason: str,
    ) -> None:
        """Initialize exception.

        Args:
            component: Scoring component that failed.
            reason: Why scoring failed.
        """
        super().__init__(
            f"Scoring error for '{component}': {reason}",
            details={"component": component, "reason": reason},
        )


# ============================================================================
# Output Errors
# ============================================================================


class OutputError(FengShuiAgentError):
    """Error during output generation."""

    pass


class JsonValidationError(OutputError):
    """JSON output failed validation.

    Raised when the generated JSON doesn't match the expected schema.
    """

    def __init__(
        self,
        validation_errors: list[str],
    ) -> None:
        """Initialize exception.

        Args:
            validation_errors: List of validation error messages.
        """
        super().__init__(
            f"JSON validation failed: {len(validation_errors)} errors",
            details={"validation_errors": validation_errors},
        )
        self.validation_errors = validation_errors


class OutputSizeError(OutputError):
    """Output exceeds size limit.

    Raised when generated JSON is too large.
    """

    def __init__(
        self,
        actual_size: int,
        max_size: int,
    ) -> None:
        """Initialize exception.

        Args:
            actual_size: Actual output size in bytes.
            max_size: Maximum allowed size in bytes.
        """
        super().__init__(
            f"Output size {actual_size} bytes exceeds maximum {max_size} bytes",
            details={"actual_size": actual_size, "max_size": max_size},
        )


# ============================================================================
# Safety Errors
# ============================================================================


class SafetyError(FengShuiAgentError):
    """Safety-critical error.

    Raised for issues that could affect physical safety.
    """

    pass


class EmergencyExitBlockedError(SafetyError):
    """Emergency exit path is blocked.

    Raised when furniture placement blocks the path to an exit.
    """

    def __init__(
        self,
        blocking_furniture: list[str],
    ) -> None:
        """Initialize exception.

        Args:
            blocking_furniture: List of furniture IDs blocking exit.
        """
        super().__init__(
            "Emergency exit path is blocked by furniture",
            details={"blocking_furniture": blocking_furniture},
        )
        self.blocking_furniture = blocking_furniture


class DoorBlockedError(SafetyError):
    """Door cannot open fully.

    Raised when furniture prevents a door from opening.
    """

    def __init__(
        self,
        door_wall: str,
        blocking_furniture: str,
    ) -> None:
        """Initialize exception.

        Args:
            door_wall: Wall where blocked door is located.
            blocking_furniture: Furniture ID blocking the door.
        """
        super().__init__(
            f"Door on {door_wall} wall blocked by furniture '{blocking_furniture}'",
            details={
                "door_wall": door_wall,
                "blocking_furniture": blocking_furniture,
            },
        )
