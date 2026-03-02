"""Unit tests for feng_shui_checker service using a 4m x 5m sample room."""

import pytest

from src.modules.layout.application.services.feng_shui_checker import (
    FengShuiViolation,
    _rule_bed_headboard_solid_wall,
    _rule_bed_not_facing_door,
    _rule_mirror_not_facing_bed,
    _rule_no_bed_under_window,
    _rule_wealth_corner_not_empty,
    check_feng_shui,
)
from src.modules.layout.application.services.spatial_resolver import PhysicalPlacement, RoomSpec
from src.modules.layout.domain.entities.room import DoorPosition, WallSide, WindowPosition
from src.modules.layout.infrastructure.geometry.collision import AABB

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_placement(
    fid: str, x: float, z: float, w: float, l: float, rotation: int = 0
) -> PhysicalPlacement:
    return PhysicalPlacement(
        furniture_id=fid,
        x=x,
        y=0.0,
        z=z,
        rotation=rotation,
        bbox=AABB.from_position_and_size(x=x, z=z, width=w, depth=l),
    )


@pytest.fixture
def room() -> RoomSpec:
    """4 m wide (x) x 5 m deep (z) room with south door and east window."""
    return RoomSpec(
        width=4.0,
        depth=5.0,
        doors=[DoorPosition(wall=WallSide.SOUTH, offset=1.5, width=0.9)],
        windows=[WindowPosition(wall=WallSide.EAST, offset=1.0, width=1.2)],
    )


# ---------------------------------------------------------------------------
# bed_not_facing_door
# ---------------------------------------------------------------------------


class TestBedNotFacingDoor:
    def test_bed_facing_south_door_violation(self, room: RoomSpec) -> None:
        """Bed foot at z<1m near south door → violation."""
        bed = _make_placement("bed_01", x=1.0, z=0.05, w=2.0, l=1.9, rotation=180)
        result = _rule_bed_not_facing_door(bed, room)
        assert not result.passed
        assert result.severity == "critical"

    def test_bed_far_from_door_passes(self, room: RoomSpec) -> None:
        """Bed foot at z>1m from south door → passes."""
        bed = _make_placement("bed_01", x=1.0, z=1.5, w=2.0, l=1.9, rotation=180)
        result = _rule_bed_not_facing_door(bed, room)
        assert result.passed

    def test_no_bed_skips_rule(self, room: RoomSpec) -> None:
        result = _rule_bed_not_facing_door(None, room)
        assert result.passed

    def test_no_door_skips_rule(self) -> None:
        room_no_door = RoomSpec(width=4.0, depth=5.0)
        bed = _make_placement("bed_01", x=1.0, z=0.1, w=2.0, l=1.9)
        result = _rule_bed_not_facing_door(bed, room_no_door)
        assert result.passed


# ---------------------------------------------------------------------------
# bed_headboard_solid_wall
# ---------------------------------------------------------------------------


class TestBedHeadboardSolidWall:
    def test_headboard_against_south_wall_no_window_passes(self, room: RoomSpec) -> None:
        """South wall has no window → headboard against it is fine."""
        bed = _make_placement("bed_01", x=1.0, z=0.0, w=2.0, l=1.9, rotation=180)
        result = _rule_bed_headboard_solid_wall(bed, room)
        assert result.passed

    def test_headboard_against_east_wall_with_window_violation(self, room: RoomSpec) -> None:
        """East wall has a window at z=[1.0, 2.2]; bed overlapping that span → violation."""
        bed = _make_placement("bed_01", x=3.5, z=1.0, w=0.5, l=1.9, rotation=270)
        result = _rule_bed_headboard_solid_wall(bed, room)
        assert not result.passed
        assert result.severity == "major"

    def test_headboard_not_near_any_wall_violation(self, room: RoomSpec) -> None:
        """Bed floating in middle of room → headboard not near wall."""
        bed = _make_placement("bed_01", x=1.0, z=2.0, w=2.0, l=1.9, rotation=180)
        result = _rule_bed_headboard_solid_wall(bed, room)
        assert not result.passed

    def test_no_bed_skips_rule(self, room: RoomSpec) -> None:
        result = _rule_bed_headboard_solid_wall(None, room)
        assert result.passed


# ---------------------------------------------------------------------------
# desk_facing_door
# ---------------------------------------------------------------------------


class TestDeskFacingDoor:
    def test_desk_clear_sight_to_door(self, room: RoomSpec) -> None:
        """Desk with no obstructions between it and door → passes."""
        placements = [_make_placement("desk_01", x=0.1, z=3.5, w=1.2, l=0.6)]
        violations = check_feng_shui(placements, room)
        desk_rule = next(v for v in violations if v.rule_id == "desk_facing_door")
        assert desk_rule.passed

    def test_no_desk_skips_rule(self, room: RoomSpec) -> None:
        placements = [_make_placement("bed_01", x=1.0, z=1.5, w=2.0, l=1.9, rotation=180)]
        violations = check_feng_shui(placements, room)
        desk_rule = next(v for v in violations if v.rule_id == "desk_facing_door")
        assert desk_rule.passed


# ---------------------------------------------------------------------------
# wealth_corner_not_empty
# ---------------------------------------------------------------------------


class TestWealthCornerNotEmpty:
    def test_wealth_corner_empty_violation(self, room: RoomSpec) -> None:
        """All items in SW corner → SE wealth corner empty → violation."""
        placements = [_make_placement("chair_01", x=0.1, z=0.1, w=0.6, l=0.6)]
        result = _rule_wealth_corner_not_empty(placements, room)
        assert not result.passed
        assert result.severity == "major"

    def test_wealth_corner_occupied_passes(self, room: RoomSpec) -> None:
        """Item in SE quadrant (x>2.4, z>3.0) → passes."""
        placements = [_make_placement("plant_01", x=2.5, z=3.1, w=0.3, l=0.3)]
        result = _rule_wealth_corner_not_empty(placements, room)
        assert result.passed


# ---------------------------------------------------------------------------
# mirror_not_facing_bed
# ---------------------------------------------------------------------------


class TestMirrorNotFacingBed:
    def test_mirror_facing_bed_violation(self) -> None:
        """Mirror sharing x-range with bed → violation."""
        bed = _make_placement("bed_01", x=1.0, z=2.0, w=2.0, l=1.9)
        mirror = _make_placement("mirror_01", x=1.5, z=0.5, w=0.5, l=0.1)
        result = _rule_mirror_not_facing_bed(mirror, bed)
        assert not result.passed
        assert result.severity == "major"

    def test_mirror_not_facing_bed_passes(self) -> None:
        """Mirror with no x-overlap with bed → passes."""
        bed = _make_placement("bed_01", x=2.0, z=2.0, w=2.0, l=1.9)
        mirror = _make_placement("mirror_01", x=0.0, z=0.5, w=0.5, l=0.1)
        result = _rule_mirror_not_facing_bed(mirror, bed)
        assert result.passed

    def test_no_mirror_skips_rule(self) -> None:
        bed = _make_placement("bed_01", x=1.0, z=2.0, w=2.0, l=1.9)
        result = _rule_mirror_not_facing_bed(None, bed)
        assert result.passed

    def test_no_bed_skips_rule(self) -> None:
        mirror = _make_placement("mirror_01", x=1.0, z=0.5, w=0.5, l=0.1)
        result = _rule_mirror_not_facing_bed(mirror, None)
        assert result.passed


# ---------------------------------------------------------------------------
# no_bed_under_window
# ---------------------------------------------------------------------------


class TestNoBedUnderWindow:
    def test_bed_under_east_window_violation(self, room: RoomSpec) -> None:
        """East window at z=[1.0, 2.2]. Bed spanning z=[1.0, 2.9] → violation."""
        bed = _make_placement("bed_01", x=3.5, z=1.0, w=0.5, l=1.9, rotation=270)
        result = _rule_no_bed_under_window(bed, room)
        assert not result.passed
        assert result.severity == "major"

    def test_bed_away_from_window_passes(self, room: RoomSpec) -> None:
        """East window at z=[1.0, 2.2]. Bed at z=[3.0, 3.9] has no overlap → passes."""
        bed = _make_placement("bed_01", x=0.5, z=3.0, w=1.5, l=0.9, rotation=180)
        result = _rule_no_bed_under_window(bed, room)
        assert result.passed

    def test_no_bed_skips_rule(self, room: RoomSpec) -> None:
        result = _rule_no_bed_under_window(None, room)
        assert result.passed


# ---------------------------------------------------------------------------
# Full integration: check_feng_shui
# ---------------------------------------------------------------------------


class TestCheckFengShuiIntegration:
    def test_returns_six_violations(self, room: RoomSpec) -> None:
        """check_feng_shui should always return exactly 6 violation results."""
        placements = [
            _make_placement("bed_01", x=1.0, z=1.5, w=2.0, l=1.9, rotation=180),
            _make_placement("desk_01", x=0.1, z=3.5, w=1.2, l=0.6),
            _make_placement("plant_01", x=2.5, z=3.1, w=0.3, l=0.3),
        ]
        violations = check_feng_shui(placements, room)
        assert len(violations) == 6

    def test_all_violations_have_rule_id(self, room: RoomSpec) -> None:
        placements = [_make_placement("bed_01", x=1.0, z=1.5, w=2.0, l=1.9, rotation=180)]
        violations = check_feng_shui(placements, room)
        assert all(v.rule_id for v in violations)

    def test_violation_dataclass_is_frozen(self) -> None:
        v = FengShuiViolation(rule_id="x", passed=True, severity="minor", suggestion="ok")
        with pytest.raises((AttributeError, TypeError)):
            v.passed = False  # type: ignore
