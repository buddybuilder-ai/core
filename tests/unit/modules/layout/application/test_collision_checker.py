"""Unit tests for collision_checker service using a 4m x 5m sample room."""

import pytest

from src.modules.layout.application.services.collision_checker import (
    DOOR_CLEARANCE,
    WALKWAY_CLEARANCE,
    Collision,
    check_collisions,
)
from src.modules.layout.application.services.spatial_resolver import PhysicalPlacement, RoomSpec
from src.modules.layout.domain.entities.room import DoorPosition, WallSide, WindowPosition
from src.modules.layout.infrastructure.geometry.collision import AABB

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_placement(fid: str, x: float, z: float, w: float, depth: float) -> PhysicalPlacement:
    return PhysicalPlacement(
        furniture_id=fid,
        x=x, y=0.0, z=z,
        rotation=0,
        bbox=AABB.from_position_and_size(x=x, z=z, width=w, depth=depth),
    )


@pytest.fixture
def room() -> RoomSpec:
    """4 m wide (x) x 5 m deep (z) room."""
    return RoomSpec(
        width=4.0,
        depth=5.0,
        doors=[DoorPosition(wall=WallSide.SOUTH, offset=1.5, width=0.9)],
        windows=[WindowPosition(wall=WallSide.EAST, offset=1.0, width=1.2)],
    )


# ---------------------------------------------------------------------------
# Clean layout
# ---------------------------------------------------------------------------


class TestNoCollisions:
    def test_no_collisions_clean_layout(self, room: RoomSpec) -> None:
        """Two well-spaced items should produce zero collisions."""
        placements = [
            _make_placement("bed_01",  0.1, 2.5, 2.0, 1.9),
            _make_placement("desk_01", 0.1, 0.9, 1.2, 0.6),
        ]
        results = check_collisions(placements, room)
        assert results == []


# ---------------------------------------------------------------------------
# Out-of-bounds
# ---------------------------------------------------------------------------


class TestOutOfBounds:
    def test_item_extending_east(self, room: RoomSpec) -> None:
        """Item partially outside east wall → critical out_of_bounds."""
        placements = [_make_placement("wardrobe_01", 3.5, 1.0, 1.0, 0.6)]
        results = check_collisions(placements, room)
        assert any(c.type == "out_of_bounds" and c.severity == "critical" for c in results)

    def test_item_at_negative_x(self, room: RoomSpec) -> None:
        """Item starting at negative x → critical out_of_bounds."""
        placements = [_make_placement("sofa_01", -0.5, 1.0, 2.0, 0.9)]
        results = check_collisions(placements, room)
        assert any(c.type == "out_of_bounds" for c in results)

    def test_item_fully_inside_no_bounds_issue(self, room: RoomSpec) -> None:
        """Item fully inside room → no out_of_bounds collision."""
        placements = [_make_placement("chair_01", 0.5, 0.5, 0.6, 0.6)]
        results = check_collisions(placements, room)
        assert not any(c.type == "out_of_bounds" for c in results)


# ---------------------------------------------------------------------------
# Overlaps
# ---------------------------------------------------------------------------


class TestOverlap:
    def test_overlap_detected(self, room: RoomSpec) -> None:
        """Two overlapping items → critical overlap collision."""
        placements = [
            _make_placement("bed_01",  0.5, 2.0, 2.0, 1.9),
            _make_placement("desk_01", 1.0, 2.5, 1.2, 0.6),
        ]
        results = check_collisions(placements, room)
        overlaps = [c for c in results if c.type == "overlap"]
        assert len(overlaps) >= 1
        assert overlaps[0].severity == "critical"
        assert "bed_01" in overlaps[0].furniture_ids
        assert "desk_01" in overlaps[0].furniture_ids

    def test_overlap_description_mentions_axis(self, room: RoomSpec) -> None:
        """Overlap description should mention axis and measurement."""
        placements = [
            _make_placement("a_01", 0.0, 0.5, 2.0, 1.0),
            _make_placement("b_01", 1.0, 0.5, 2.0, 1.0),
        ]
        results = check_collisions(placements, room)
        overlaps = [c for c in results if c.type == "overlap"]
        assert any("axis" in c.description for c in overlaps)

    def test_no_overlap_adjacent_items(self, room: RoomSpec) -> None:
        """Items exactly adjacent (touching) should not be flagged as overlap."""
        placements = [
            _make_placement("a_01", 0.0, 1.0, 1.0, 1.0),
            _make_placement("b_01", 1.0, 1.0, 1.0, 1.0),
        ]
        results = check_collisions(placements, room)
        assert not any(c.type == "overlap" for c in results)


# ---------------------------------------------------------------------------
# Door clearance
# ---------------------------------------------------------------------------


class TestDoorClearance:
    def test_door_clearance_violation(self, room: RoomSpec) -> None:
        """Item inside 80 cm door clearance zone → critical door_blocked."""
        placements = [_make_placement("chair_01", 1.6, 0.1, 0.6, 0.6)]
        results = check_collisions(placements, room)
        blocked = [c for c in results if c.type == "door_blocked"]
        assert len(blocked) >= 1
        assert blocked[0].severity == "critical"

    def test_item_behind_clearance_zone_ok(self, room: RoomSpec) -> None:
        """Item just beyond 80 cm zone should not be flagged."""
        placements = [_make_placement("chair_01", 1.6, DOOR_CLEARANCE + 0.05, 0.6, 0.6)]
        results = check_collisions(placements, room)
        assert not any(c.type == "door_blocked" for c in results)

    def test_item_away_from_door_laterally_ok(self, room: RoomSpec) -> None:
        """Item in z-range of door clearance but outside door x-range should be OK."""
        placements = [_make_placement("vase_01", 0.1, 0.1, 0.3, 0.3)]
        results = check_collisions(placements, room)
        assert not any(c.type == "door_blocked" for c in results)


# ---------------------------------------------------------------------------
# Walkway clearance
# ---------------------------------------------------------------------------


class TestWalkwayClearance:
    def test_walkway_violation(self, room: RoomSpec) -> None:
        """Gap of 0.4 m (< 60 cm) → major insufficient_clearance."""
        placements = [
            _make_placement("bed_01",  0.1, 1.5, 2.0, 1.9),
            _make_placement("desk_01", 0.1, 3.8, 1.2, 0.6),  # 3.8 - (1.5+1.9) = 0.4m gap
        ]
        results = check_collisions(placements, room)
        clearance = [c for c in results if c.type == "insufficient_clearance"]
        assert len(clearance) >= 1
        assert clearance[0].severity == "major"

    def test_adequate_walkway_no_violation(self, room: RoomSpec) -> None:
        """Gap of WALKWAY_CLEARANCE + 0.1 m should not be flagged."""
        gap = WALKWAY_CLEARANCE + 0.1
        placements = [
            _make_placement("a_01", 0.1, 1.0, 1.0, 1.0),
            _make_placement("b_01", 0.1, 1.0 + 1.0 + gap, 1.0, 1.0),
        ]
        results = check_collisions(placements, room)
        assert not any(c.type == "insufficient_clearance" for c in results)

    def test_overlapping_items_not_flagged_as_clearance(self, room: RoomSpec) -> None:
        """Overlapping items should be flagged as overlap, not clearance violation."""
        placements = [
            _make_placement("a_01", 0.0, 1.0, 2.0, 1.0),
            _make_placement("b_01", 1.0, 1.0, 2.0, 1.0),
        ]
        results = check_collisions(placements, room)
        types = {c.type for c in results}
        assert "overlap" in types
        assert "insufficient_clearance" not in types


# ---------------------------------------------------------------------------
# Collision data structure
# ---------------------------------------------------------------------------


class TestCollisionDataClass:
    def test_collision_fields(self) -> None:
        c = Collision(type="overlap", severity="critical",
                      furniture_ids=["a", "b"], description="test overlap")
        assert c.type == "overlap"
        assert c.severity == "critical"
        assert "a" in c.furniture_ids

    def test_collision_is_frozen(self) -> None:
        c = Collision(type="overlap", severity="critical", furniture_ids=["a"], description="x")
        with pytest.raises((AttributeError, TypeError)):
            c.type = "other"  # type: ignore
