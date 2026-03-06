"""Unit tests for spatial_resolver service using a 4m x 5m sample room."""

import pytest

from src.modules.layout.application.services.spatial_resolver import (
    FurnitureSize,
    RoomSpec,
    SemanticPlacement,
    SpatialResolver,
)
from src.modules.layout.domain.entities.room import DoorPosition, WallSide, WindowPosition


@pytest.fixture
def room() -> RoomSpec:
    """4 m wide (x) x 5 m deep (z) room with one south door and one east window."""
    return RoomSpec(
        width=4.0,
        depth=5.0,
        doors=[DoorPosition(wall=WallSide.SOUTH, offset=1.5, width=0.9)],
        windows=[WindowPosition(wall=WallSide.EAST, offset=1.0, width=1.2)],
    )


@pytest.fixture
def resolver() -> SpatialResolver:
    return SpatialResolver()


# ---------------------------------------------------------------------------
# Wall placement tests
# ---------------------------------------------------------------------------


class TestSouthWallPlacement:
    def test_center_alignment_position(self, resolver: SpatialResolver, room: RoomSpec) -> None:
        """Bed on south wall, centered: x should be (4 - 2) / 2 = 1.0, z should be gap."""
        bed = SemanticPlacement(
            furniture_id="bed_01",
            furniture_type="bed",
            size=FurnitureSize(w=2.0, length=1.9, h=0.5),
            target_wall="south",
            alignment="center",
            offset_from_wall=0.05,
            priority=1,
        )
        results = resolver.resolve([bed], room)
        p = results[0]
        assert p.furniture_id == "bed_01"
        assert p.x == pytest.approx(1.0)
        assert p.z == pytest.approx(0.05)
        assert p.rotation == 180
        assert p.y == 0.0

    def test_left_alignment(self, resolver: SpatialResolver, room: RoomSpec) -> None:
        """Left alignment starts at x=0."""
        sem = SemanticPlacement(
            furniture_id="nightstand_01",
            furniture_type="nightstand",
            size=FurnitureSize(w=0.5, length=0.5, h=0.6),
            target_wall="south",
            alignment="left",
            offset_from_wall=0.0,
            priority=2,
        )
        results = resolver.resolve([sem], room)
        assert results[0].x == pytest.approx(0.0)

    def test_right_alignment(self, resolver: SpatialResolver, room: RoomSpec) -> None:
        """Right alignment places right edge against east side."""
        sem = SemanticPlacement(
            furniture_id="nightstand_02",
            furniture_type="nightstand",
            size=FurnitureSize(w=0.5, length=0.5, h=0.6),
            target_wall="south",
            alignment="right",
            offset_from_wall=0.0,
            priority=2,
        )
        results = resolver.resolve([sem], room)
        assert results[0].x == pytest.approx(3.5)  # 4.0 - 0.5


class TestNorthWallPlacement:
    def test_left_alignment_wardrobe(self, resolver: SpatialResolver, room: RoomSpec) -> None:
        """Wardrobe left of north wall: x=0, z = depth - size.length - gap."""
        wardrobe = SemanticPlacement(
            furniture_id="wardrobe_01",
            furniture_type="wardrobe",
            size=FurnitureSize(w=1.2, length=0.6, h=2.0),
            target_wall="north",
            alignment="left",
            offset_from_wall=0.05,
            priority=1,
        )
        results = resolver.resolve([wardrobe], room)
        p = results[0]
        assert p.x == pytest.approx(0.0)
        assert p.z == pytest.approx(5.0 - 0.6 - 0.05)
        # wardrobe is in _FORCE_INWARD_TYPES → forced to face inward.
        # north wall → opposite = south → _FACING_ROTATION["south"] = 180
        assert p.rotation == 180

    def test_bbox_reaches_north_wall(self, resolver: SpatialResolver, room: RoomSpec) -> None:
        """Item against north wall with no gap: max_z should equal room depth."""
        sem = SemanticPlacement(
            furniture_id="shelf_01",
            furniture_type="shelf",
            size=FurnitureSize(w=1.0, length=0.3, h=1.8),
            target_wall="north",
            alignment="center",
            offset_from_wall=0.0,
            priority=1,
        )
        results = resolver.resolve([sem], room)
        assert results[0].bbox.max_z == pytest.approx(5.0)


class TestEastWallPlacement:
    def test_position(self, resolver: SpatialResolver, room: RoomSpec) -> None:
        """Item against east wall: max_x should approach room width."""
        sem = SemanticPlacement(
            furniture_id="dresser_01",
            furniture_type="dresser",
            size=FurnitureSize(w=0.5, length=1.0, h=1.2),
            target_wall="east",
            alignment="center",
            offset_from_wall=0.0,
            priority=1,
        )
        results = resolver.resolve([sem], room)
        p = results[0]
        assert p.bbox.max_x == pytest.approx(4.0)
        assert p.rotation == 270


class TestWestWallPlacement:
    def test_position(self, resolver: SpatialResolver, room: RoomSpec) -> None:
        """Item against west wall: min_x should be at gap."""
        sem = SemanticPlacement(
            furniture_id="bookcase_01",
            furniture_type="bookcase",
            size=FurnitureSize(w=0.3, length=1.0, h=2.0),
            target_wall="west",
            alignment="left",
            offset_from_wall=0.0,
            priority=1,
        )
        results = resolver.resolve([sem], room)
        p = results[0]
        assert p.bbox.min_x == pytest.approx(0.0)
        assert p.rotation == 90


# ---------------------------------------------------------------------------
# Center placement
# ---------------------------------------------------------------------------


class TestCenterPlacement:
    def test_item_in_room_center(self, resolver: SpatialResolver, room: RoomSpec) -> None:
        """Center-placed item: footprint centered in room."""
        sem = SemanticPlacement(
            furniture_id="table_01",
            furniture_type="table",
            size=FurnitureSize(w=1.2, length=0.8, h=0.75),
            target_wall="center",
            alignment="center",
            offset_from_wall=0.0,
            priority=1,
        )
        results = resolver.resolve([sem], room)
        p = results[0]
        assert p.x == pytest.approx((4.0 - 1.2) / 2.0)
        assert p.z == pytest.approx((5.0 - 0.8) / 2.0)
        assert p.rotation == 0


# ---------------------------------------------------------------------------
# Priority ordering
# ---------------------------------------------------------------------------


class TestPriorityOrdering:
    def test_priority_1_comes_first(self, resolver: SpatialResolver, room: RoomSpec) -> None:
        """Items should be returned sorted by ascending priority."""
        items = [
            SemanticPlacement(
                furniture_id="desk_01",
                furniture_type="desk",
                size=FurnitureSize(w=1.2, length=0.6, h=0.75),
                target_wall="north",
                alignment="center",
                offset_from_wall=0.05,
                priority=2,
            ),
            SemanticPlacement(
                furniture_id="bed_01",
                furniture_type="bed",
                size=FurnitureSize(w=2.0, length=1.9, h=0.5),
                target_wall="south",
                alignment="center",
                offset_from_wall=0.05,
                priority=1,
            ),
        ]
        results = resolver.resolve(items, room)
        assert results[0].furniture_id == "bed_01"
        assert results[1].furniture_id == "desk_01"


# ---------------------------------------------------------------------------
# Clamping
# ---------------------------------------------------------------------------


class TestClamping:
    def test_oversized_item_clamped(self, resolver: SpatialResolver, room: RoomSpec) -> None:
        """An item wider than the room should be clamped to fit."""
        sem = SemanticPlacement(
            furniture_id="giant_sofa_01",
            furniture_type="sofa",
            size=FurnitureSize(w=10.0, length=1.0, h=0.9),
            target_wall="south",
            alignment="center",
            offset_from_wall=0.0,
            priority=1,
        )
        results = resolver.resolve([sem], room)
        p = results[0]
        assert p.x >= 0.0
        assert p.bbox.max_x <= room.width


# ---------------------------------------------------------------------------
# BBox integrity
# ---------------------------------------------------------------------------


class TestBBoxIntegrity:
    def test_bbox_dimensions_match_size(self, resolver: SpatialResolver, room: RoomSpec) -> None:
        """AABB width and depth should match furniture size (adjusted for rotation)."""
        sem = SemanticPlacement(
            furniture_id="bed_01",
            furniture_type="bed",
            size=FurnitureSize(w=2.0, length=1.9, h=0.5),
            target_wall="south",
            alignment="center",
            offset_from_wall=0.05,
            priority=1,
        )
        results = resolver.resolve([sem], room)
        p = results[0]
        # rotation=180 → footprint unchanged (w=2.0, length=1.9)
        assert p.bbox.width == pytest.approx(2.0)
        assert p.bbox.depth == pytest.approx(1.9)

    def test_rotated_item_swaps_dimensions(self, resolver: SpatialResolver, room: RoomSpec) -> None:
        """Item against east/west wall has width/depth swapped."""
        sem = SemanticPlacement(
            furniture_id="dresser_01",
            furniture_type="dresser",
            size=FurnitureSize(w=1.5, length=0.5, h=1.2),
            target_wall="east",
            alignment="center",
            offset_from_wall=0.0,
            priority=1,
        )
        results = resolver.resolve([sem], room)
        p = results[0]
        # rotation=270 → footprint is (l, w) = (0.5, 1.5)
        assert p.bbox.width == pytest.approx(0.5)
        assert p.bbox.depth == pytest.approx(1.5)
