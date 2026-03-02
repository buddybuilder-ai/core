"""Tests for domain value objects."""

import pytest

from src.modules.layout.domain.value_objects.coordinates import (
    BoundingBox,
    Position3D,
    Rotation,
)
from src.modules.layout.domain.value_objects.feng_shui_score import FengShuiScore
from src.modules.layout.domain.value_objects.rule_priority import RulePriority


class TestRotation:
    """Tests for Rotation enum."""

    def test_rotation_values(self) -> None:
        """Test rotation enum has correct values."""
        assert Rotation.DEG_0 == 0
        assert Rotation.DEG_90 == 90
        assert Rotation.DEG_180 == 180
        assert Rotation.DEG_270 == 270

    @pytest.mark.parametrize(
        ("degrees", "expected"),
        [
            (0, Rotation.DEG_0),
            (30, Rotation.DEG_0),
            (45, Rotation.DEG_90),
            (90, Rotation.DEG_90),
            (135, Rotation.DEG_180),
            (180, Rotation.DEG_180),
            (225, Rotation.DEG_270),
            (270, Rotation.DEG_270),
            (315, Rotation.DEG_0),
            (360, Rotation.DEG_0),
            (450, Rotation.DEG_90),
        ],
    )
    def test_from_degrees(self, degrees: float, expected: Rotation) -> None:
        """Test conversion from degrees to rotation enum."""
        assert Rotation.from_degrees(degrees) == expected


class TestPosition3D:
    """Tests for Position3D value object."""

    def test_create_position(self) -> None:
        """Test creating a 3D position."""
        pos = Position3D(x=1.5, y=2.0, z=3.5)
        assert pos.x == 1.5
        assert pos.y == 2.0
        assert pos.z == 3.5

    def test_position_is_immutable(self) -> None:
        """Test that position cannot be modified."""
        pos = Position3D(x=1.0, y=2.0, z=3.0)
        with pytest.raises(AttributeError):
            pos.x = 5.0  # type: ignore[misc]

    def test_origin(self) -> None:
        """Test creating origin position."""
        origin = Position3D.origin()
        assert origin.x == 0.0
        assert origin.y == 0.0
        assert origin.z == 0.0

    def test_distance_to(self) -> None:
        """Test 3D distance calculation."""
        p1 = Position3D(x=0, y=0, z=0)
        p2 = Position3D(x=3, y=4, z=0)
        assert p1.distance_to(p2) == 5.0

    def test_distance_2d(self) -> None:
        """Test 2D distance calculation (floor plane)."""
        p1 = Position3D(x=0, y=5, z=0)
        p2 = Position3D(x=3, y=10, z=4)
        assert p1.distance_2d(p2) == 5.0

    def test_translate(self) -> None:
        """Test position translation."""
        pos = Position3D(x=1, y=2, z=3)
        new_pos = pos.translate(dx=1, dy=2, dz=3)
        assert new_pos.x == 2
        assert new_pos.y == 4
        assert new_pos.z == 6
        # Original unchanged (immutable)
        assert pos.x == 1

    def test_invalid_type_raises_error(self) -> None:
        """Test that invalid coordinate types raise TypeError."""
        with pytest.raises(TypeError):
            Position3D(x="1", y=2, z=3)  # type: ignore[arg-type]


class TestBoundingBox:
    """Tests for BoundingBox value object."""

    def test_create_bounding_box(self) -> None:
        """Test creating a bounding box."""
        bbox = BoundingBox(
            min_x=0,
            min_y=0,
            min_z=0,
            max_x=2,
            max_y=3,
            max_z=4,
        )
        assert bbox.width == 2
        assert bbox.height == 3
        assert bbox.depth == 4

    def test_invalid_bounds_raises_error(self) -> None:
        """Test that invalid bounds raise ValueError."""
        with pytest.raises(ValueError, match="min_x"):
            BoundingBox(min_x=5, min_y=0, min_z=0, max_x=2, max_y=3, max_z=4)

    def test_center(self) -> None:
        """Test center calculation."""
        bbox = BoundingBox(
            min_x=0,
            min_y=0,
            min_z=0,
            max_x=4,
            max_y=6,
            max_z=8,
        )
        center = bbox.center
        assert center.x == 2
        assert center.y == 3
        assert center.z == 4

    def test_floor_area(self) -> None:
        """Test floor area calculation."""
        bbox = BoundingBox(
            min_x=0,
            min_y=0,
            min_z=0,
            max_x=3,
            max_y=2,
            max_z=4,
        )
        assert bbox.floor_area == 12  # 3 * 4

    def test_volume(self) -> None:
        """Test volume calculation."""
        bbox = BoundingBox(
            min_x=0,
            min_y=0,
            min_z=0,
            max_x=2,
            max_y=3,
            max_z=4,
        )
        assert bbox.volume == 24  # 2 * 3 * 4

    def test_intersects(self) -> None:
        """Test 3D intersection detection."""
        bbox1 = BoundingBox(min_x=0, min_y=0, min_z=0, max_x=2, max_y=2, max_z=2)
        bbox2 = BoundingBox(min_x=1, min_y=1, min_z=1, max_x=3, max_y=3, max_z=3)
        bbox3 = BoundingBox(min_x=5, min_y=5, min_z=5, max_x=6, max_y=6, max_z=6)

        assert bbox1.intersects(bbox2) is True
        assert bbox1.intersects(bbox3) is False

    def test_intersects_2d(self) -> None:
        """Test 2D intersection detection (floor plane)."""
        bbox1 = BoundingBox(min_x=0, min_y=0, min_z=0, max_x=2, max_y=2, max_z=2)
        bbox2 = BoundingBox(min_x=1, min_y=10, min_z=1, max_x=3, max_y=12, max_z=3)

        # Different heights but overlap on floor
        assert bbox1.intersects_2d(bbox2) is True
        assert bbox1.intersects(bbox2) is False

    def test_contains_point(self) -> None:
        """Test point containment."""
        bbox = BoundingBox(min_x=0, min_y=0, min_z=0, max_x=2, max_y=2, max_z=2)

        assert bbox.contains_point(Position3D(1, 1, 1)) is True
        assert bbox.contains_point(Position3D(0, 0, 0)) is True  # boundary
        assert bbox.contains_point(Position3D(3, 1, 1)) is False

    def test_expand(self) -> None:
        """Test bounding box expansion."""
        bbox = BoundingBox(min_x=1, min_y=1, min_z=1, max_x=3, max_y=3, max_z=3)
        expanded = bbox.expand(0.5)

        assert expanded.min_x == 0.5
        assert expanded.max_x == 3.5
        assert expanded.width == 3  # 2 + 0.5 + 0.5

    def test_from_center_and_size(self) -> None:
        """Test creating bbox from center and size."""
        center = Position3D(x=5, y=5, z=5)
        bbox = BoundingBox.from_center_and_size(center, width=4, height=2, depth=6)

        assert bbox.min_x == 3
        assert bbox.max_x == 7
        assert bbox.center.x == 5

    def test_from_position_and_size(self) -> None:
        """Test creating bbox from corner position and size."""
        pos = Position3D(x=1, y=2, z=3)
        bbox = BoundingBox.from_position_and_size(pos, width=2, height=3, depth=4)

        assert bbox.min_x == 1
        assert bbox.max_x == 3
        assert bbox.min_y == 2
        assert bbox.max_y == 5


class TestFengShuiScore:
    """Tests for FengShuiScore value object."""

    def test_create_valid_score(self) -> None:
        """Test creating a valid feng shui score."""
        score = FengShuiScore(
            command_position=25,
            five_elements=15,
            chi_flow=20,
            sha_chi_avoidance=18,
        )
        assert score.total == 78
        assert score.grade == "B"

    def test_score_is_immutable(self) -> None:
        """Test that score cannot be modified."""
        score = FengShuiScore(
            command_position=20,
            five_elements=15,
            chi_flow=20,
            sha_chi_avoidance=15,
        )
        with pytest.raises(AttributeError):
            score.command_position = 30  # type: ignore[misc]

    def test_invalid_command_position_raises_error(self) -> None:
        """Test that out-of-range command_position raises ValueError."""
        with pytest.raises(ValueError, match="command_position"):
            FengShuiScore(
                command_position=35,  # max is 30
                five_elements=15,
                chi_flow=20,
                sha_chi_avoidance=15,
            )

    def test_invalid_type_raises_error(self) -> None:
        """Test that non-integer score raises TypeError."""
        with pytest.raises(TypeError, match="command_position"):
            FengShuiScore(
                command_position=25.5,  # type: ignore[arg-type]
                five_elements=15,
                chi_flow=20,
                sha_chi_avoidance=15,
            )

    def test_percentage(self) -> None:
        """Test percentage calculation."""
        score = FengShuiScore(
            command_position=15,
            five_elements=10,
            chi_flow=12,
            sha_chi_avoidance=13,
        )
        assert score.total == 50
        assert score.percentage == 50.0

    @pytest.mark.parametrize(
        ("total_score", "expected_grade"),
        [
            (95, "A"),
            (90, "A"),
            (85, "B"),
            (70, "B"),
            (60, "C"),
            (50, "C"),
            (45, "D"),
            (40, "D"),
            (35, "F"),
            (0, "F"),
        ],
    )
    def test_grade(self, total_score: int, expected_grade: str) -> None:
        """Test grade assignment based on total score."""
        # Create score that adds up to total_score
        score = FengShuiScore(
            command_position=min(30, total_score),
            five_elements=min(20, max(0, total_score - 30)),
            chi_flow=min(25, max(0, total_score - 50)),
            sha_chi_avoidance=min(25, max(0, total_score - 75)),
        )
        assert score.grade == expected_grade

    def test_is_acceptable(self) -> None:
        """Test is_acceptable threshold."""
        acceptable = FengShuiScore(
            command_position=20,
            five_elements=10,
            chi_flow=10,
            sha_chi_avoidance=0,
        )
        not_acceptable = FengShuiScore(
            command_position=15,
            five_elements=10,
            chi_flow=10,
            sha_chi_avoidance=0,
        )

        assert acceptable.is_acceptable is True
        assert not_acceptable.is_acceptable is False

    def test_get_weakest_component(self) -> None:
        """Test identifying weakest scoring component."""
        score = FengShuiScore(
            command_position=30,  # 100%
            five_elements=10,  # 50%
            chi_flow=25,  # 100%
            sha_chi_avoidance=5,  # 20% - weakest
        )
        assert score.get_weakest_component() == "sha_chi_avoidance"

    def test_get_improvement_suggestions(self) -> None:
        """Test getting improvement suggestions."""
        low_score = FengShuiScore(
            command_position=5,
            five_elements=5,
            chi_flow=5,
            sha_chi_avoidance=5,
        )
        suggestions = low_score.get_improvement_suggestions()
        assert len(suggestions) == 4

    def test_zero_score(self) -> None:
        """Test creating zero score."""
        score = FengShuiScore.zero()
        assert score.total == 0

    def test_perfect_score(self) -> None:
        """Test creating perfect score."""
        score = FengShuiScore.perfect()
        assert score.total == 100
        assert score.grade == "A"


class TestRulePriority:
    """Tests for RulePriority enum."""

    def test_priority_values(self) -> None:
        """Test priority enum values."""
        assert RulePriority.MUST_NOT_VIOLATE == 1
        assert RulePriority.SHOULD_DO == 2
        assert RulePriority.RECOMMENDED == 3

    def test_priority_ordering(self) -> None:
        """Test that higher priority has lower value."""
        assert RulePriority.MUST_NOT_VIOLATE < RulePriority.SHOULD_DO
        assert RulePriority.SHOULD_DO < RulePriority.RECOMMENDED

    def test_description(self) -> None:
        """Test priority descriptions."""
        assert "Critical" in RulePriority.MUST_NOT_VIOLATE.description
        assert "Important" in RulePriority.SHOULD_DO.description
        assert "Recommended" in RulePriority.RECOMMENDED.description

    def test_weight(self) -> None:
        """Test priority weights."""
        assert RulePriority.MUST_NOT_VIOLATE.weight == 1.0
        assert RulePriority.SHOULD_DO.weight == 0.6
        assert RulePriority.RECOMMENDED.weight == 0.3

    def test_is_critical(self) -> None:
        """Test is_critical check."""
        assert RulePriority.MUST_NOT_VIOLATE.is_critical() is True
        assert RulePriority.SHOULD_DO.is_critical() is False

    def test_is_important(self) -> None:
        """Test is_important check."""
        assert RulePriority.MUST_NOT_VIOLATE.is_important() is True
        assert RulePriority.SHOULD_DO.is_important() is True
        assert RulePriority.RECOMMENDED.is_important() is False
