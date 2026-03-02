"""Tests for domain exceptions."""

import pytest

from src.modules.layout.domain.exceptions import (
    ClearanceViolationError,
    CollisionError,
    DoorBlockedError,
    EmergencyExitBlockedError,
    FengShuiAgentError,
    FurnitureDbError,
    InsufficientSpaceError,
    InvalidDoorPositionError,
    InvalidRoomDimensionsError,
    InvalidWindowPositionError,
    JsonValidationError,
    NoValidPlacementError,
    OutputError,
    OutputSizeError,
    PlacementError,
    RagSearchError,
    SafetyError,
    ScoringError,
    ToolError,
    ToolExecutionError,
    ToolInputError,
    ToolTimeoutError,
    ValidationError,
)


class TestFengShuiAgentError:
    """Tests for base FengShuiAgentError."""

    def test_create_base_error(self) -> None:
        """Test creating base error."""
        error = FengShuiAgentError("Something went wrong")
        assert error.message == "Something went wrong"
        assert error.details == {}

    def test_create_error_with_details(self) -> None:
        """Test creating error with details."""
        error = FengShuiAgentError(
            "Error occurred",
            details={"key": "value", "count": 42},
        )
        assert error.message == "Error occurred"
        assert error.details["key"] == "value"
        assert error.details["count"] == 42

    def test_str_without_details(self) -> None:
        """Test string representation without details."""
        error = FengShuiAgentError("Simple error")
        assert str(error) == "Simple error"

    def test_str_with_details(self) -> None:
        """Test string representation with details."""
        error = FengShuiAgentError("Error", details={"info": "test"})
        assert "Error" in str(error)
        assert "info" in str(error)

    def test_exception_can_be_raised_and_caught(self) -> None:
        """Test that exception works with try/except."""
        with pytest.raises(FengShuiAgentError) as exc_info:
            raise FengShuiAgentError("Test error", details={"test": True})

        assert exc_info.value.message == "Test error"


class TestValidationErrors:
    """Tests for validation error classes."""

    def test_validation_error_inheritance(self) -> None:
        """Test ValidationError inherits from base."""
        error = ValidationError("Validation failed")
        assert isinstance(error, FengShuiAgentError)

    def test_invalid_room_dimensions_error(self) -> None:
        """Test InvalidRoomDimensionsError."""
        error = InvalidRoomDimensionsError(
            dimension="width",
            value=-5.0,
            reason="must be positive",
        )
        assert error.dimension == "width"
        assert error.value == -5.0
        assert "width" in str(error)
        assert "-5.0" in str(error)

    def test_invalid_door_position_error(self) -> None:
        """Test InvalidDoorPositionError."""
        error = InvalidDoorPositionError(
            wall="south",
            offset=6.0,
            room_dimension=5.0,
        )
        assert "south" in str(error)
        assert "6.0" in str(error)
        assert error.details["room_dimension"] == 5.0

    def test_invalid_window_position_error(self) -> None:
        """Test InvalidWindowPositionError."""
        error = InvalidWindowPositionError(
            wall="east",
            offset=5.0,
            room_dimension=4.0,
        )
        assert "east" in str(error)
        assert error.details["offset"] == 5.0


class TestPlacementErrors:
    """Tests for placement error classes."""

    def test_placement_error_inheritance(self) -> None:
        """Test PlacementError inherits from base."""
        error = PlacementError("Placement failed")
        assert isinstance(error, FengShuiAgentError)

    def test_no_valid_placement_error(self) -> None:
        """Test NoValidPlacementError."""
        error = NoValidPlacementError(
            furniture_id="bed_001",
            furniture_name="Queen Bed",
            reason="room too small",
            attempts=10,
        )
        assert error.furniture_id == "bed_001"
        assert error.furniture_name == "Queen Bed"
        assert "Queen Bed" in str(error)
        assert error.details["attempts"] == 10

    def test_insufficient_space_error(self) -> None:
        """Test InsufficientSpaceError."""
        error = InsufficientSpaceError(
            room_area=15.0,
            required_area=25.0,
            furniture_list=["bed", "wardrobe", "desk"],
        )
        assert "15.0" in str(error)
        assert "25.0" in str(error)
        assert len(error.details["furniture_list"]) == 3

    def test_collision_error(self) -> None:
        """Test CollisionError."""
        error = CollisionError(
            furniture_id="sofa_001",
            collides_with="coffee_table_001",
            collision_type="furniture",
        )
        assert "sofa_001" in str(error)
        assert "coffee_table_001" in str(error)

    def test_clearance_violation_error(self) -> None:
        """Test ClearanceViolationError."""
        error = ClearanceViolationError(
            location="between sofa and wall",
            actual_clearance=0.4,
            required_clearance=0.6,
        )
        assert "0.40" in str(error)
        assert "0.60" in str(error)


class TestToolErrors:
    """Tests for tool error classes."""

    def test_tool_error_inheritance(self) -> None:
        """Test ToolError inherits from base."""
        error = ToolError("Tool failed")
        assert isinstance(error, FengShuiAgentError)

    def test_tool_input_error(self) -> None:
        """Test ToolInputError."""
        error = ToolInputError(
            tool_name="SPATIAL_CALCULATOR",
            field="room_dimensions",
            reason="missing required field",
        )
        assert "SPATIAL_CALCULATOR" in str(error)
        assert "room_dimensions" in str(error)

    def test_tool_execution_error(self) -> None:
        """Test ToolExecutionError."""
        original = ValueError("Original error")
        error = ToolExecutionError(
            tool_name="COLLISION_DETECTOR",
            reason="calculation overflow",
            original_error=original,
        )
        assert error.original_error is original
        assert "COLLISION_DETECTOR" in str(error)

    def test_tool_timeout_error(self) -> None:
        """Test ToolTimeoutError."""
        error = ToolTimeoutError(
            tool_name="RAG_SEARCH",
            timeout_seconds=30.0,
        )
        assert "30.0" in str(error)
        assert "RAG_SEARCH" in str(error)

    def test_rag_search_error(self) -> None:
        """Test RagSearchError."""
        error = RagSearchError(
            query="feng shui bedroom rules",
            reason="vector store unavailable",
        )
        assert "feng shui bedroom rules" in str(error)
        assert error.details["reason"] == "vector store unavailable"

    def test_furniture_db_error(self) -> None:
        """Test FurnitureDbError."""
        error = FurnitureDbError(
            query_params={"room_type": "bedroom", "category": "bed"},
            reason="connection refused",
        )
        assert "connection refused" in str(error)
        assert error.details["query_params"]["room_type"] == "bedroom"


class TestScoringError:
    """Tests for ScoringError."""

    def test_scoring_error(self) -> None:
        """Test ScoringError."""
        error = ScoringError(
            component="command_position",
            reason="no furniture to evaluate",
        )
        assert "command_position" in str(error)
        assert error.details["reason"] == "no furniture to evaluate"


class TestOutputErrors:
    """Tests for output error classes."""

    def test_output_error_inheritance(self) -> None:
        """Test OutputError inherits from base."""
        error = OutputError("Output failed")
        assert isinstance(error, FengShuiAgentError)

    def test_json_validation_error(self) -> None:
        """Test JsonValidationError."""
        errors = [
            "field 'position' is required",
            "field 'rotation' must be a number",
        ]
        error = JsonValidationError(validation_errors=errors)
        assert error.validation_errors == errors
        assert "2 errors" in str(error)

    def test_output_size_error(self) -> None:
        """Test OutputSizeError."""
        error = OutputSizeError(
            actual_size=2_000_000,
            max_size=1_000_000,
        )
        assert "2000000" in str(error)
        assert "1000000" in str(error)


class TestSafetyErrors:
    """Tests for safety error classes."""

    def test_safety_error_inheritance(self) -> None:
        """Test SafetyError inherits from base."""
        error = SafetyError("Safety issue")
        assert isinstance(error, FengShuiAgentError)

    def test_emergency_exit_blocked_error(self) -> None:
        """Test EmergencyExitBlockedError."""
        error = EmergencyExitBlockedError(
            blocking_furniture=["sofa_001", "bookshelf_001"],
        )
        assert error.blocking_furniture == ["sofa_001", "bookshelf_001"]
        assert "Emergency exit" in str(error)

    def test_door_blocked_error(self) -> None:
        """Test DoorBlockedError."""
        error = DoorBlockedError(
            door_wall="south",
            blocking_furniture="wardrobe_001",
        )
        assert "south" in str(error)
        assert "wardrobe_001" in str(error)


class TestExceptionHierarchy:
    """Tests for exception hierarchy."""

    def test_catching_by_base_class(self) -> None:
        """Test that derived exceptions can be caught by base class."""
        exceptions = [
            InvalidRoomDimensionsError("width", -1, "must be positive"),
            NoValidPlacementError("id", "name", "reason"),
            ToolExecutionError("tool", "reason"),
            JsonValidationError(["error"]),
            EmergencyExitBlockedError(["furniture"]),
        ]

        for exc in exceptions:
            with pytest.raises(FengShuiAgentError):
                raise exc

    def test_validation_errors_caught_together(self) -> None:
        """Test that all validation errors can be caught together."""
        validation_exceptions = [
            InvalidRoomDimensionsError("width", -1, "must be positive"),
            InvalidDoorPositionError("south", 10, 5),
            InvalidWindowPositionError("east", 10, 5),
        ]

        for exc in validation_exceptions:
            with pytest.raises(ValidationError):
                raise exc

    def test_placement_errors_caught_together(self) -> None:
        """Test that all placement errors can be caught together."""
        placement_exceptions = [
            NoValidPlacementError("id", "name", "reason"),
            InsufficientSpaceError(10, 20, []),
            CollisionError("a", "b"),
            ClearanceViolationError("loc", 0.4, 0.6),
        ]

        for exc in placement_exceptions:
            with pytest.raises(PlacementError):
                raise exc

    def test_tool_errors_caught_together(self) -> None:
        """Test that all tool errors can be caught together."""
        tool_exceptions = [
            ToolInputError("tool", "field", "reason"),
            ToolExecutionError("tool", "reason"),
            ToolTimeoutError("tool", 30),
            RagSearchError("query", "reason"),
            FurnitureDbError({}, "reason"),
        ]

        for exc in tool_exceptions:
            with pytest.raises(ToolError):
                raise exc

    def test_safety_errors_caught_together(self) -> None:
        """Test that all safety errors can be caught together."""
        safety_exceptions = [
            EmergencyExitBlockedError([]),
            DoorBlockedError("south", "furniture"),
        ]

        for exc in safety_exceptions:
            with pytest.raises(SafetyError):
                raise exc
