"""Tests for feng shui Pydantic schemas."""

import pytest
from pydantic import ValidationError

from src.schemas.layout.feng_shui import (
    CommandPosition,
    DoorPosition,
    ElementBalance,
    FengShuiAnalysis,
    FengShuiRecommendation,
    FengShuiRule,
    FengShuiScoreBreakdown,
    FiveElement,
    FurnitureDimensions,
    RoomType,
    RulePriority,
    ShaChiLine,
    WallSide,
    WindowPosition,
)


class TestEnums:
    """Tests for enum types."""

    def test_room_type_values(self) -> None:
        """Test RoomType enum values."""
        assert RoomType.BEDROOM == "bedroom"
        assert RoomType.LIVING_ROOM == "living_room"
        assert RoomType.OFFICE == "office"

    def test_five_element_values(self) -> None:
        """Test FiveElement enum values."""
        assert FiveElement.WOOD == "wood"
        assert FiveElement.FIRE == "fire"
        assert FiveElement.EARTH == "earth"
        assert FiveElement.METAL == "metal"
        assert FiveElement.WATER == "water"

    def test_rule_priority_values(self) -> None:
        """Test RulePriority enum values."""
        assert RulePriority.MUST_NOT_VIOLATE == 1
        assert RulePriority.SHOULD_DO == 2
        assert RulePriority.RECOMMENDED == 3

    def test_wall_side_values(self) -> None:
        """Test WallSide enum values."""
        assert WallSide.NORTH == "north"
        assert WallSide.SOUTH == "south"


class TestDoorPosition:
    """Tests for DoorPosition schema."""

    def test_valid_door_position(self) -> None:
        """Test creating valid door position."""
        door = DoorPosition(wall=WallSide.SOUTH, offset=2.0, width=0.9)
        assert door.wall == WallSide.SOUTH
        assert door.offset == 2.0
        assert door.width == 0.9
        assert door.swing_inward is True

    def test_door_with_string_wall(self) -> None:
        """Test creating door with string wall value."""
        door = DoorPosition(wall="north", offset=1.0)
        assert door.wall == WallSide.NORTH

    def test_invalid_negative_offset(self) -> None:
        """Test that negative offset raises error."""
        with pytest.raises(ValidationError) as exc_info:
            DoorPosition(wall=WallSide.SOUTH, offset=-1.0)
        assert "offset" in str(exc_info.value)

    def test_invalid_zero_width(self) -> None:
        """Test that zero width raises error."""
        with pytest.raises(ValidationError) as exc_info:
            DoorPosition(wall=WallSide.SOUTH, offset=1.0, width=0)
        assert "width" in str(exc_info.value)


class TestWindowPosition:
    """Tests for WindowPosition schema."""

    def test_valid_window_position(self) -> None:
        """Test creating valid window position."""
        window = WindowPosition(wall=WallSide.EAST, offset=1.5, width=1.5)
        assert window.wall == WallSide.EAST
        assert window.offset == 1.5
        assert window.width == 1.5
        assert window.height == 1.2  # default
        assert window.sill_height == 0.9  # default

    def test_window_with_custom_height(self) -> None:
        """Test creating window with custom height."""
        window = WindowPosition(
            wall=WallSide.WEST, offset=0.5, width=2.0, height=1.8, sill_height=0.6
        )
        assert window.height == 1.8
        assert window.sill_height == 0.6


class TestFurnitureDimensions:
    """Tests for FurnitureDimensions schema."""

    def test_valid_dimensions(self) -> None:
        """Test creating valid dimensions."""
        dims = FurnitureDimensions(width=2.0, depth=1.0, height=0.8)
        assert dims.width == 2.0
        assert dims.depth == 1.0
        assert dims.height == 0.8

    def test_floor_area_property(self) -> None:
        """Test floor area calculation."""
        dims = FurnitureDimensions(width=2.0, depth=1.5, height=0.8)
        assert dims.floor_area == 3.0

    def test_invalid_zero_dimension(self) -> None:
        """Test that zero dimensions raise error."""
        with pytest.raises(ValidationError):
            FurnitureDimensions(width=0, depth=1.0, height=0.8)


class TestFengShuiRule:
    """Tests for FengShuiRule schema."""

    def test_valid_rule(self) -> None:
        """Test creating valid rule."""
        rule = FengShuiRule(
            rule_id="rule_001",
            description="Bed should not face door directly",
            priority=RulePriority.MUST_NOT_VIOLATE,
            room_types=[RoomType.BEDROOM],
        )
        assert rule.rule_id == "rule_001"
        assert rule.priority == RulePriority.MUST_NOT_VIOLATE

    def test_empty_description_raises_error(self) -> None:
        """Test that empty description raises error."""
        with pytest.raises(ValidationError) as exc_info:
            FengShuiRule(
                rule_id="rule_001",
                description="   ",  # whitespace only
                priority=RulePriority.RECOMMENDED,
            )
        assert "Description cannot be empty" in str(exc_info.value)


class TestFengShuiScoreBreakdown:
    """Tests for FengShuiScoreBreakdown schema."""

    def test_valid_score(self) -> None:
        """Test creating valid score."""
        score = FengShuiScoreBreakdown(
            command_position=25,
            five_elements_balance=15,
            chi_flow=20,
            sha_chi_avoidance=18,
        )
        assert score.command_position == 25
        assert score.total == 78

    def test_total_property(self) -> None:
        """Test total calculation."""
        score = FengShuiScoreBreakdown(
            command_position=30,
            five_elements_balance=20,
            chi_flow=25,
            sha_chi_avoidance=25,
        )
        assert score.total == 100

    def test_grade_property(self) -> None:
        """Test grade calculation."""
        # A grade (>=90)
        score_a = FengShuiScoreBreakdown(
            command_position=30,
            five_elements_balance=20,
            chi_flow=25,
            sha_chi_avoidance=20,
        )
        assert score_a.grade == "A"

        # B grade (>=70)
        score_b = FengShuiScoreBreakdown(
            command_position=20,
            five_elements_balance=15,
            chi_flow=20,
            sha_chi_avoidance=15,
        )
        assert score_b.grade == "B"

        # F grade (<40)
        score_f = FengShuiScoreBreakdown(
            command_position=10,
            five_elements_balance=5,
            chi_flow=10,
            sha_chi_avoidance=10,
        )
        assert score_f.grade == "F"

    def test_is_acceptable_property(self) -> None:
        """Test is_acceptable threshold."""
        acceptable = FengShuiScoreBreakdown(
            command_position=15,
            five_elements_balance=10,
            chi_flow=10,
            sha_chi_avoidance=5,
        )
        assert acceptable.is_acceptable is True

        not_acceptable = FengShuiScoreBreakdown(
            command_position=10,
            five_elements_balance=10,
            chi_flow=10,
            sha_chi_avoidance=5,
        )
        assert not_acceptable.is_acceptable is False

    def test_score_out_of_range(self) -> None:
        """Test that out-of-range scores raise error."""
        with pytest.raises(ValidationError):
            FengShuiScoreBreakdown(
                command_position=35,  # max is 30
                five_elements_balance=15,
                chi_flow=20,
                sha_chi_avoidance=15,
            )


class TestElementBalance:
    """Tests for ElementBalance schema."""

    def test_default_values(self) -> None:
        """Test default values are zero."""
        balance = ElementBalance()
        assert balance.wood == 0
        assert balance.fire == 0
        assert balance.total_elements == 0

    def test_total_elements(self) -> None:
        """Test total elements count."""
        balance = ElementBalance(wood=2, fire=1, earth=1)
        assert balance.total_elements == 4

    def test_unique_elements(self) -> None:
        """Test unique elements count."""
        balance = ElementBalance(wood=2, fire=1, earth=1)
        assert balance.unique_elements == 3

    def test_is_balanced(self) -> None:
        """Test is_balanced check."""
        balanced = ElementBalance(wood=1, fire=1, earth=1)
        assert balanced.is_balanced is True

        unbalanced = ElementBalance(wood=3, fire=1)
        assert unbalanced.is_balanced is False

    def test_to_dict(self) -> None:
        """Test to_dict method."""
        balance = ElementBalance(wood=2, fire=1)
        d = balance.to_dict()
        assert d["wood"] == 2
        assert d["fire"] == 1
        assert d["water"] == 0


class TestCommandPosition:
    """Tests for CommandPosition schema."""

    def test_valid_command_position(self) -> None:
        """Test creating valid command position."""
        cp = CommandPosition(
            furniture_id="bed_001",
            is_in_position=True,
            can_see_door=True,
            has_wall_backing=True,
            distance_from_ideal=0.5,
        )
        assert cp.furniture_id == "bed_001"
        assert cp.is_in_position is True
        assert cp.distance_from_ideal == 0.5


class TestShaChiLine:
    """Tests for ShaChiLine schema."""

    def test_valid_sha_chi_line(self) -> None:
        """Test creating valid sha chi line."""
        line = ShaChiLine(
            from_element="door_south",
            to_element="window_north",
            intensity=7,
            mitigation="Place a plant or screen between door and window",
        )
        assert line.from_element == "door_south"
        assert line.intensity == 7

    def test_intensity_range(self) -> None:
        """Test intensity must be 1-10."""
        with pytest.raises(ValidationError):
            ShaChiLine(from_element="a", to_element="b", intensity=0)
        with pytest.raises(ValidationError):
            ShaChiLine(from_element="a", to_element="b", intensity=11)


class TestFengShuiRecommendation:
    """Tests for FengShuiRecommendation schema."""

    def test_valid_recommendation(self) -> None:
        """Test creating valid recommendation."""
        rec = FengShuiRecommendation(
            category="command_position",
            description="Move bed to northwest corner",
            priority=RulePriority.SHOULD_DO,
            expected_improvement=10,
        )
        assert rec.category == "command_position"
        assert rec.expected_improvement == 10


class TestFengShuiAnalysis:
    """Tests for FengShuiAnalysis schema."""

    def test_valid_analysis(self) -> None:
        """Test creating valid analysis."""
        analysis = FengShuiAnalysis(
            score=FengShuiScoreBreakdown(
                command_position=25,
                five_elements_balance=15,
                chi_flow=20,
                sha_chi_avoidance=18,
            ),
            command_positions=[
                CommandPosition(
                    furniture_id="bed_001",
                    is_in_position=True,
                    can_see_door=True,
                    has_wall_backing=True,
                )
            ],
            element_balance=ElementBalance(wood=2, fire=1, earth=1, metal=1),
            recommendations=[
                FengShuiRecommendation(
                    category="elements",
                    description="Add water element",
                )
            ],
            warnings=["Direct line between door and window detected"],
        )
        assert analysis.score.total == 78
        assert len(analysis.command_positions) == 1
        assert analysis.element_balance.unique_elements == 4
        assert len(analysis.warnings) == 1

    def test_analysis_with_defaults(self) -> None:
        """Test analysis with default values."""
        analysis = FengShuiAnalysis(
            score=FengShuiScoreBreakdown(
                command_position=20,
                five_elements_balance=10,
                chi_flow=15,
                sha_chi_avoidance=15,
            )
        )
        assert analysis.command_positions == []
        assert analysis.sha_chi_lines == []
        assert analysis.recommendations == []
        assert analysis.warnings == []
        assert analysis.metadata == {}


class TestSchemaValidation:
    """Tests for schema validation edge cases."""

    def test_json_serialization(self) -> None:
        """Test that schemas can be serialized to JSON."""
        score = FengShuiScoreBreakdown(
            command_position=25,
            five_elements_balance=15,
            chi_flow=20,
            sha_chi_avoidance=18,
        )
        json_str = score.model_dump_json()
        assert '"command_position":25' in json_str

    def test_json_deserialization(self) -> None:
        """Test that schemas can be deserialized from JSON."""
        json_data = {
            "command_position": 25,
            "five_elements_balance": 15,
            "chi_flow": 20,
            "sha_chi_avoidance": 18,
        }
        score = FengShuiScoreBreakdown.model_validate(json_data)
        assert score.total == 78

    def test_nested_schema_validation(self) -> None:
        """Test nested schema validation."""
        analysis_data = {
            "score": {
                "command_position": 25,
                "five_elements_balance": 15,
                "chi_flow": 20,
                "sha_chi_avoidance": 18,
            },
            "element_balance": {"wood": 2, "fire": 1},
        }
        analysis = FengShuiAnalysis.model_validate(analysis_data)
        assert analysis.score.total == 78
        assert analysis.element_balance.wood == 2
