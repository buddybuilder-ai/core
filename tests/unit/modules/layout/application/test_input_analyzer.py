"""Tests for Input Analyzer Service."""

import pytest

from src.modules.layout.application.services import (
    InputAnalyzer,
    InputAnalysisResult,
    ValidationIssue,
    ValidationSeverity,
)
from src.modules.layout.application.dtos import AgentPhase


class TestValidationIssue:
    """Tests for ValidationIssue dataclass."""

    def test_create_issue(self) -> None:
        """Test creating validation issue."""
        issue = ValidationIssue(
            field="room_type",
            message="Room type is required",
            severity=ValidationSeverity.ERROR,
        )
        assert issue.field == "room_type"
        assert issue.severity == ValidationSeverity.ERROR

    def test_to_dict(self) -> None:
        """Test converting to dictionary."""
        issue = ValidationIssue(
            field="dimensions.width",
            message="Width is too small",
            severity=ValidationSeverity.WARNING,
            suggestion="Use at least 2m",
        )
        result = issue.to_dict()
        assert result["field"] == "dimensions.width"
        assert result["severity"] == "warning"
        assert result["suggestion"] == "Use at least 2m"


class TestInputAnalysisResult:
    """Tests for InputAnalysisResult dataclass."""

    def test_has_errors(self) -> None:
        """Test has_errors property."""
        result = InputAnalysisResult(
            is_valid=False,
            issues=[
                ValidationIssue("field", "error", ValidationSeverity.ERROR),
            ],
        )
        assert result.has_errors

    def test_has_warnings(self) -> None:
        """Test has_warnings property."""
        result = InputAnalysisResult(
            is_valid=True,
            issues=[
                ValidationIssue("field", "warning", ValidationSeverity.WARNING),
            ],
        )
        assert result.has_warnings
        assert not result.has_errors

    def test_error_messages(self) -> None:
        """Test error_messages property."""
        result = InputAnalysisResult(
            is_valid=False,
            issues=[
                ValidationIssue("f1", "Error 1", ValidationSeverity.ERROR),
                ValidationIssue("f2", "Warning 1", ValidationSeverity.WARNING),
                ValidationIssue("f3", "Error 2", ValidationSeverity.ERROR),
            ],
        )
        errors = result.error_messages
        assert len(errors) == 2
        assert "Error 1" in errors
        assert "Error 2" in errors


class TestInputAnalyzer:
    """Tests for InputAnalyzer service."""

    @pytest.fixture
    def analyzer(self) -> InputAnalyzer:
        """Create input analyzer instance."""
        return InputAnalyzer()

    @pytest.fixture
    def valid_input(self) -> dict:
        """Create valid input data."""
        return {
            "room_type": "bedroom",
            "dimensions": {"width": 5.0, "depth": 4.0, "height": 2.8},
            "doors": [{"wall": "south", "offset": 2.0, "width": 0.9}],
            "windows": [{"wall": "east", "offset": 1.5, "width": 1.5, "height": 1.2}],
        }

    def test_analyze_valid_input(
        self, analyzer: InputAnalyzer, valid_input: dict
    ) -> None:
        """Test analyzing valid input."""
        result = analyzer.analyze(valid_input)
        assert result.is_valid
        assert result.room is not None
        assert result.room_type_str == "bedroom"
        assert len(result.doors) == 1
        assert len(result.windows) == 1

    def test_analyze_missing_room_type(self, analyzer: InputAnalyzer) -> None:
        """Test analyzing input without room type."""
        input_data = {
            "dimensions": {"width": 5.0, "depth": 4.0},
            "doors": [{"wall": "south", "offset": 2.0}],
        }
        result = analyzer.analyze(input_data)
        assert not result.is_valid
        assert result.has_errors
        assert any("room type" in e.lower() for e in result.error_messages)

    def test_analyze_invalid_room_type(self, analyzer: InputAnalyzer) -> None:
        """Test analyzing input with invalid room type."""
        input_data = {
            "room_type": "bathroom",  # Not supported
            "dimensions": {"width": 5.0, "depth": 4.0},
        }
        result = analyzer.analyze(input_data)
        assert not result.is_valid
        assert any("unknown room type" in e.lower() for e in result.error_messages)

    def test_analyze_room_type_variations(self, analyzer: InputAnalyzer) -> None:
        """Test different room type spellings."""
        variations = [
            ("living_room", True),
            ("livingroom", True),
            ("living", True),
            ("office", True),
            ("study", True),
            ("home_office", True),
            ("dining_room", True),
            ("diningroom", True),
            ("BEDROOM", True),  # Case insensitive
        ]
        for room_type, should_be_valid in variations:
            input_data = {
                "room_type": room_type,
                "dimensions": {"width": 5.0, "depth": 4.0},
                "doors": [{"wall": "south", "offset": 2.0}],
            }
            result = analyzer.analyze(input_data)
            assert result.is_valid == should_be_valid, f"Failed for {room_type}"

    def test_analyze_missing_dimensions(self, analyzer: InputAnalyzer) -> None:
        """Test analyzing input without dimensions."""
        input_data = {"room_type": "bedroom"}
        result = analyzer.analyze(input_data)
        assert not result.is_valid
        assert any("width" in e.lower() for e in result.error_messages)

    def test_analyze_dimensions_too_small(self, analyzer: InputAnalyzer) -> None:
        """Test analyzing with dimensions below minimum."""
        input_data = {
            "room_type": "bedroom",
            "dimensions": {"width": 1.5, "depth": 1.5},  # Below 2m minimum
        }
        result = analyzer.analyze(input_data)
        assert not result.is_valid
        assert any("too small" in e.lower() for e in result.error_messages)

    def test_analyze_dimensions_large(self, analyzer: InputAnalyzer) -> None:
        """Test analyzing with very large dimensions (warning)."""
        input_data = {
            "room_type": "living_room",
            "dimensions": {"width": 25.0, "depth": 15.0},  # Above 20m
            "doors": [{"wall": "south", "offset": 2.0}],
        }
        result = analyzer.analyze(input_data)
        # Should still be valid but with warnings
        assert result.has_warnings

    def test_analyze_flat_dimensions(self, analyzer: InputAnalyzer) -> None:
        """Test analyzing with flat dimension structure."""
        input_data = {
            "room_type": "office",
            "width": 4.0,
            "depth": 3.0,
            "doors": [{"wall": "south", "offset": 1.5}],
        }
        result = analyzer.analyze(input_data)
        assert result.is_valid
        assert result.room is not None
        assert result.room.width == 4.0

    def test_analyze_missing_doors(self, analyzer: InputAnalyzer) -> None:
        """Test analyzing without doors (warning)."""
        input_data = {
            "room_type": "bedroom",
            "dimensions": {"width": 5.0, "depth": 4.0},
        }
        result = analyzer.analyze(input_data)
        assert result.is_valid  # No doors is a warning, not error
        assert result.has_warnings

    def test_analyze_invalid_door_wall(self, analyzer: InputAnalyzer) -> None:
        """Test analyzing with invalid door wall."""
        input_data = {
            "room_type": "bedroom",
            "dimensions": {"width": 5.0, "depth": 4.0},
            "doors": [{"wall": "up", "offset": 2.0}],  # Invalid wall
        }
        result = analyzer.analyze(input_data)
        # Invalid doors are skipped with error
        assert len(result.doors) == 0

    def test_analyze_door_negative_offset(self, analyzer: InputAnalyzer) -> None:
        """Test analyzing with negative door offset."""
        input_data = {
            "room_type": "bedroom",
            "dimensions": {"width": 5.0, "depth": 4.0},
            "doors": [{"wall": "south", "offset": -1.0}],
        }
        result = analyzer.analyze(input_data)
        assert len(result.doors) == 0  # Invalid door skipped

    def test_analyze_door_beyond_wall(self, analyzer: InputAnalyzer) -> None:
        """Test analyzing with door extending beyond wall."""
        input_data = {
            "room_type": "bedroom",
            "dimensions": {"width": 5.0, "depth": 4.0},
            "doors": [{"wall": "south", "offset": 4.5, "width": 0.9}],  # 4.5 + 0.9 > 5.0
        }
        result = analyzer.analyze(input_data)
        assert result.has_warnings

    def test_analyze_missing_windows(self, analyzer: InputAnalyzer) -> None:
        """Test analyzing without windows (info)."""
        input_data = {
            "room_type": "bedroom",
            "dimensions": {"width": 5.0, "depth": 4.0},
            "doors": [{"wall": "south", "offset": 2.0}],
        }
        result = analyzer.analyze(input_data)
        assert result.is_valid

    def test_analyze_window_validation(self, analyzer: InputAnalyzer) -> None:
        """Test window validation."""
        input_data = {
            "room_type": "bedroom",
            "dimensions": {"width": 5.0, "depth": 4.0},
            "doors": [{"wall": "south", "offset": 2.0}],
            "windows": [
                {"wall": "east", "offset": 1.0, "width": 1.5},
                {"wall": "north", "offset": 0.5, "width": 2.0, "height": 1.5},
            ],
        }
        result = analyzer.analyze(input_data)
        assert result.is_valid
        assert len(result.windows) == 2

    def test_analyze_preferences(self, analyzer: InputAnalyzer) -> None:
        """Test extracting preferences."""
        input_data = {
            "room_type": "bedroom",
            "dimensions": {"width": 5.0, "depth": 4.0},
            "doors": [{"wall": "south", "offset": 2.0}],
            "preferences": {
                "budget_level": "high",
                "style_preference": "traditional",
                "natural_light_priority": "very_important",
                "accessibility_needs": ["wheelchair_accessible"],
            },
        }
        result = analyzer.analyze(input_data)
        assert result.preferences.budget_level == "high"
        assert result.preferences.style_preference == "traditional"
        assert result.preferences.natural_light_priority == "very_important"
        assert "wheelchair_accessible" in result.preferences.accessibility_needs

    def test_analyze_elongated_room_warning(self, analyzer: InputAnalyzer) -> None:
        """Test warning for elongated room."""
        input_data = {
            "room_type": "office",
            "dimensions": {"width": 2.5, "depth": 12.0},  # 4.8:1 ratio
            "doors": [{"wall": "south", "offset": 1.0}],
        }
        result = analyzer.analyze(input_data)
        assert result.has_warnings
        assert any("elongated" in w.lower() for w in result.warning_messages)

    def test_analyze_low_ceiling_warning(self, analyzer: InputAnalyzer) -> None:
        """Test warning for low ceiling height."""
        input_data = {
            "room_type": "bedroom",
            "dimensions": {"width": 5.0, "depth": 4.0, "height": 2.0},
            "doors": [{"wall": "south", "offset": 2.0}],
        }
        result = analyzer.analyze(input_data)
        assert result.has_warnings

    def test_create_context_from_valid_result(
        self, analyzer: InputAnalyzer, valid_input: dict
    ) -> None:
        """Test creating context from valid analysis result."""
        result = analyzer.analyze(valid_input)
        context = analyzer.create_context(result)

        assert context.room is not None
        assert context.room_type == "bedroom"
        assert context.phase == AgentPhase.INITIALIZATION

    def test_create_context_from_invalid_result(
        self, analyzer: InputAnalyzer
    ) -> None:
        """Test creating context from invalid analysis raises error."""
        result = InputAnalysisResult(is_valid=False, room=None)
        with pytest.raises(ValueError):
            analyzer.create_context(result)

    def test_create_context_includes_warnings(
        self, analyzer: InputAnalyzer
    ) -> None:
        """Test that context includes warnings from analysis."""
        input_data = {
            "room_type": "bedroom",
            "dimensions": {"width": 2.0, "depth": 10.0},  # 5:1 ratio - very elongated
            "doors": [{"wall": "south", "offset": 0.5}],
        }
        result = analyzer.analyze(input_data)
        context = analyzer.create_context(result)

        # Context should have warnings (elongated room warning)
        assert len(context.validation_warnings) > 0

    def test_analyze_invalid_dimension_type(self, analyzer: InputAnalyzer) -> None:
        """Test analyzing with invalid dimension types."""
        input_data = {
            "room_type": "bedroom",
            "dimensions": {"width": "five", "depth": 4.0},  # String instead of number
        }
        result = analyzer.analyze(input_data)
        assert not result.is_valid

    def test_analyze_doors_not_list(self, analyzer: InputAnalyzer) -> None:
        """Test analyzing with doors as non-list."""
        input_data = {
            "room_type": "bedroom",
            "dimensions": {"width": 5.0, "depth": 4.0},
            "doors": {"wall": "south", "offset": 2.0},  # Dict instead of list
        }
        result = analyzer.analyze(input_data)
        assert result.has_errors

    def test_result_to_dict(self, analyzer: InputAnalyzer, valid_input: dict) -> None:
        """Test converting result to dictionary."""
        result = analyzer.analyze(valid_input)
        d = result.to_dict()
        assert d["is_valid"] is True
        assert d["room_type"] == "bedroom"
        assert "issues" in d
