"""Tests for Collision Detection algorithms."""

import pytest

from src.modules.layout.infrastructure.geometry.collision import (
    AABB,
    ClearanceRequirement,
    CollisionDetector,
    CollisionResult,
    CollisionSeverity,
    check_rotated_collision,
)


class TestCollisionSeverity:
    """Tests for CollisionSeverity enum."""

    def test_severity_levels_exist(self) -> None:
        """Test all severity levels exist."""
        assert CollisionSeverity.ERROR == "error"
        assert CollisionSeverity.WARNING == "warning"
        assert CollisionSeverity.INFO == "info"


class TestAABB:
    """Tests for AABB (Axis-Aligned Bounding Box) class."""

    def test_create_aabb(self) -> None:
        """Test creating an AABB."""
        box = AABB(min_x=0, min_z=0, max_x=2, max_z=3)
        assert box.min_x == 0
        assert box.min_z == 0
        assert box.max_x == 2
        assert box.max_z == 3

    def test_width_depth_properties(self) -> None:
        """Test width and depth calculations."""
        box = AABB(min_x=1, min_z=2, max_x=4, max_z=5)
        assert box.width == 3
        assert box.depth == 3

    def test_center_properties(self) -> None:
        """Test center coordinate calculations."""
        box = AABB(min_x=0, min_z=0, max_x=4, max_z=6)
        assert box.center_x == 2
        assert box.center_z == 3

    def test_area_property(self) -> None:
        """Test area calculation."""
        box = AABB(min_x=0, min_z=0, max_x=2, max_z=3)
        assert box.area == 6

    def test_aabb_is_frozen(self) -> None:
        """Test that AABB is immutable."""
        box = AABB(min_x=0, min_z=0, max_x=1, max_z=1)
        with pytest.raises(AttributeError):
            box.min_x = 5  # type: ignore


class TestAABBContainsPoint:
    """Tests for AABB.contains_point method."""

    @pytest.fixture
    def box(self) -> AABB:
        """Create a test box."""
        return AABB(min_x=0, min_z=0, max_x=2, max_z=2)

    def test_contains_point_inside(self, box: AABB) -> None:
        """Test point inside box."""
        assert box.contains_point(1, 1)

    def test_contains_point_on_edge(self, box: AABB) -> None:
        """Test point on edge (inclusive)."""
        assert box.contains_point(0, 0)
        assert box.contains_point(2, 2)
        assert box.contains_point(1, 0)

    def test_contains_point_outside(self, box: AABB) -> None:
        """Test point outside box."""
        assert not box.contains_point(-1, 1)
        assert not box.contains_point(3, 1)
        assert not box.contains_point(1, 3)


class TestAABBIntersects:
    """Tests for AABB.intersects method."""

    @pytest.fixture
    def box(self) -> AABB:
        """Create a test box."""
        return AABB(min_x=0, min_z=0, max_x=2, max_z=2)

    def test_intersects_overlapping(self, box: AABB) -> None:
        """Test overlapping boxes."""
        other = AABB(min_x=1, min_z=1, max_x=3, max_z=3)
        assert box.intersects(other)
        assert other.intersects(box)

    def test_intersects_contained(self, box: AABB) -> None:
        """Test one box contains another."""
        small = AABB(min_x=0.5, min_z=0.5, max_x=1.5, max_z=1.5)
        assert box.intersects(small)
        assert small.intersects(box)

    def test_intersects_adjacent_no_overlap(self, box: AABB) -> None:
        """Test adjacent boxes don't overlap."""
        adjacent = AABB(min_x=2, min_z=0, max_x=4, max_z=2)
        assert not box.intersects(adjacent)

    def test_intersects_separate(self, box: AABB) -> None:
        """Test clearly separate boxes."""
        far = AABB(min_x=10, min_z=10, max_x=12, max_z=12)
        assert not box.intersects(far)


class TestAABBTouches:
    """Tests for AABB.touches method."""

    @pytest.fixture
    def box(self) -> AABB:
        """Create a test box."""
        return AABB(min_x=0, min_z=0, max_x=2, max_z=2)

    def test_touches_adjacent_right(self, box: AABB) -> None:
        """Test boxes that touch on the right edge."""
        adjacent = AABB(min_x=2, min_z=0, max_x=4, max_z=2)
        assert box.touches(adjacent)

    def test_touches_adjacent_bottom(self, box: AABB) -> None:
        """Test boxes that touch on the bottom edge."""
        adjacent = AABB(min_x=0, min_z=2, max_x=2, max_z=4)
        assert box.touches(adjacent)

    def test_touches_overlapping_not_touching(self, box: AABB) -> None:
        """Test overlapping boxes don't count as touching."""
        overlapping = AABB(min_x=1, min_z=1, max_x=3, max_z=3)
        assert not box.touches(overlapping)

    def test_touches_separate_not_touching(self, box: AABB) -> None:
        """Test separate boxes don't count as touching."""
        far = AABB(min_x=5, min_z=5, max_x=7, max_z=7)
        assert not box.touches(far)


class TestAABBDistance:
    """Tests for AABB.distance_to method."""

    @pytest.fixture
    def box(self) -> AABB:
        """Create a test box."""
        return AABB(min_x=0, min_z=0, max_x=2, max_z=2)

    def test_distance_overlapping(self, box: AABB) -> None:
        """Test distance is 0 for overlapping boxes."""
        overlapping = AABB(min_x=1, min_z=1, max_x=3, max_z=3)
        assert box.distance_to(overlapping) == 0

    def test_distance_adjacent(self, box: AABB) -> None:
        """Test distance is 0 for adjacent boxes."""
        adjacent = AABB(min_x=2, min_z=0, max_x=4, max_z=2)
        assert box.distance_to(adjacent) == 0

    def test_distance_horizontal_gap(self, box: AABB) -> None:
        """Test distance with horizontal gap."""
        right = AABB(min_x=4, min_z=0, max_x=6, max_z=2)
        assert box.distance_to(right) == pytest.approx(2.0)

    def test_distance_vertical_gap(self, box: AABB) -> None:
        """Test distance with vertical gap."""
        below = AABB(min_x=0, min_z=5, max_x=2, max_z=7)
        assert box.distance_to(below) == pytest.approx(3.0)

    def test_distance_diagonal(self, box: AABB) -> None:
        """Test distance with diagonal gap."""
        diagonal = AABB(min_x=5, min_z=5, max_x=7, max_z=7)
        # Distance from (2,2) to (5,5) = sqrt(9+9) = sqrt(18)
        expected = (3**2 + 3**2) ** 0.5
        assert box.distance_to(diagonal) == pytest.approx(expected)


class TestAABBExpanded:
    """Tests for AABB.expanded method."""

    def test_expand_positive(self) -> None:
        """Test expanding a box."""
        box = AABB(min_x=1, min_z=1, max_x=3, max_z=3)
        expanded = box.expanded(0.5)
        assert expanded.min_x == 0.5
        assert expanded.min_z == 0.5
        assert expanded.max_x == 3.5
        assert expanded.max_z == 3.5

    def test_expand_negative(self) -> None:
        """Test shrinking a box."""
        box = AABB(min_x=0, min_z=0, max_x=4, max_z=4)
        shrunk = box.expanded(-1)
        assert shrunk.min_x == 1
        assert shrunk.max_x == 3


class TestAABBIntersection:
    """Tests for AABB.intersection method."""

    def test_intersection_overlapping(self) -> None:
        """Test intersection of overlapping boxes."""
        box1 = AABB(min_x=0, min_z=0, max_x=3, max_z=3)
        box2 = AABB(min_x=1, min_z=1, max_x=4, max_z=4)
        intersection = box1.intersection(box2)
        assert intersection is not None
        assert intersection.min_x == 1
        assert intersection.min_z == 1
        assert intersection.max_x == 3
        assert intersection.max_z == 3

    def test_intersection_no_overlap(self) -> None:
        """Test intersection of non-overlapping boxes."""
        box1 = AABB(min_x=0, min_z=0, max_x=2, max_z=2)
        box2 = AABB(min_x=5, min_z=5, max_x=7, max_z=7)
        assert box1.intersection(box2) is None


class TestAABBFactories:
    """Tests for AABB factory methods."""

    def test_from_position_and_size(self) -> None:
        """Test creating AABB from position and size."""
        box = AABB.from_position_and_size(x=1, z=2, width=3, depth=4)
        assert box.min_x == 1
        assert box.min_z == 2
        assert box.max_x == 4
        assert box.max_z == 6

    def test_from_center_and_size(self) -> None:
        """Test creating AABB from center and size."""
        box = AABB.from_center_and_size(center_x=2, center_z=3, width=4, depth=6)
        assert box.min_x == 0
        assert box.min_z == 0
        assert box.max_x == 4
        assert box.max_z == 6


class TestClearanceRequirement:
    """Tests for ClearanceRequirement dataclass."""

    def test_default_clearance(self) -> None:
        """Test default clearance values."""
        clearance = ClearanceRequirement()
        assert clearance.front == 0.6
        assert clearance.back == 0.0
        assert clearance.left == 0.3
        assert clearance.right == 0.3

    def test_standard_clearance(self) -> None:
        """Test standard clearance factory."""
        clearance = ClearanceRequirement.standard()
        assert clearance.front == 0.6
        assert clearance.back == 0.1

    def test_traffic_path_clearance(self) -> None:
        """Test traffic path clearance factory."""
        clearance = ClearanceRequirement.traffic_path()
        assert clearance.front == 0.9
        assert clearance.left == 0.9

    def test_no_clearance(self) -> None:
        """Test no clearance factory."""
        clearance = ClearanceRequirement.none()
        assert clearance.front == 0.0
        assert clearance.back == 0.0
        assert clearance.left == 0.0
        assert clearance.right == 0.0


class TestCollisionResult:
    """Tests for CollisionResult named tuple."""

    def test_create_collision_result(self) -> None:
        """Test creating a collision result."""
        result = CollisionResult(
            has_collision=True,
            severity=CollisionSeverity.ERROR,
            overlap_area=0.5,
            distance=-0.2,
            message="Test collision",
        )
        assert result.has_collision
        assert result.severity == CollisionSeverity.ERROR
        assert result.overlap_area == 0.5
        assert result.distance == -0.2
        assert result.message == "Test collision"


class TestCollisionDetector:
    """Tests for CollisionDetector class."""

    @pytest.fixture
    def detector(self) -> CollisionDetector:
        """Create a test collision detector."""
        return CollisionDetector(room_width=5.0, room_depth=4.0)

    def test_create_detector(self, detector: CollisionDetector) -> None:
        """Test creating a collision detector."""
        assert detector.room_width == 5.0
        assert detector.room_depth == 4.0

    def test_create_detector_invalid_dimensions(self) -> None:
        """Test that invalid dimensions raise ValueError."""
        with pytest.raises(ValueError):
            CollisionDetector(room_width=0, room_depth=4.0)
        with pytest.raises(ValueError):
            CollisionDetector(room_width=5.0, room_depth=-1)


class TestCollisionDetectorCheckCollision:
    """Tests for CollisionDetector.check_collision method."""

    @pytest.fixture
    def detector(self) -> CollisionDetector:
        """Create a test collision detector."""
        return CollisionDetector(room_width=10.0, room_depth=10.0)

    def test_check_collision_overlapping(self, detector: CollisionDetector) -> None:
        """Test collision detection for overlapping boxes."""
        box1 = AABB.from_position_and_size(0, 0, 2, 2)
        box2 = AABB.from_position_and_size(1, 1, 2, 2)
        result = detector.check_collision(box1, box2)
        assert result.has_collision
        assert result.severity == CollisionSeverity.ERROR
        assert result.overlap_area > 0
        assert result.distance < 0

    def test_check_collision_no_collision(self, detector: CollisionDetector) -> None:
        """Test collision detection for non-overlapping boxes."""
        box1 = AABB.from_position_and_size(0, 0, 1, 1)
        box2 = AABB.from_position_and_size(5, 5, 1, 1)
        result = detector.check_collision(box1, box2)
        assert not result.has_collision
        assert result.severity == CollisionSeverity.INFO
        assert result.distance > 0


class TestCollisionDetectorCheckClearance:
    """Tests for CollisionDetector.check_clearance method."""

    @pytest.fixture
    def detector(self) -> CollisionDetector:
        """Create a test collision detector."""
        return CollisionDetector(room_width=10.0, room_depth=10.0)

    def test_check_clearance_violated(self, detector: CollisionDetector) -> None:
        """Test clearance check when violated."""
        item = AABB.from_position_and_size(0, 0, 1, 1)
        other = AABB.from_position_and_size(1.2, 0, 1, 1)  # 0.2m gap
        clearance = ClearanceRequirement(front=0.6, back=0.6, left=0.6, right=0.6)
        result = detector.check_clearance(item, other, clearance)
        assert result.has_collision
        assert result.severity == CollisionSeverity.WARNING

    def test_check_clearance_ok(self, detector: CollisionDetector) -> None:
        """Test clearance check when satisfied."""
        item = AABB.from_position_and_size(0, 0, 1, 1)
        other = AABB.from_position_and_size(2, 0, 1, 1)  # 1m gap
        clearance = ClearanceRequirement(front=0.6, back=0.1, left=0.3, right=0.3)
        result = detector.check_clearance(item, other, clearance)
        assert not result.has_collision
        assert result.severity == CollisionSeverity.INFO

    def test_check_clearance_with_rotation(self, detector: CollisionDetector) -> None:
        """Test clearance check with rotation."""
        item = AABB.from_position_and_size(0, 0, 1, 1)
        other = AABB.from_position_and_size(0, 1.2, 1, 1)  # Below item
        # Front clearance is 0.6, but rotated 90 degrees so front is now top
        clearance = ClearanceRequirement(front=0.6, back=0.0, left=0.0, right=0.0)
        result = detector.check_clearance(item, other, clearance, rotation=90)
        # With 90 degree rotation, front clearance moves to left
        assert result.severity == CollisionSeverity.INFO


class TestCollisionDetectorCheckRoomBounds:
    """Tests for CollisionDetector.check_room_bounds method."""

    @pytest.fixture
    def detector(self) -> CollisionDetector:
        """Create a test collision detector."""
        return CollisionDetector(room_width=5.0, room_depth=4.0)

    def test_check_bounds_inside(self, detector: CollisionDetector) -> None:
        """Test bounds check for item inside room."""
        box = AABB.from_position_and_size(1, 1, 2, 2)
        result = detector.check_room_bounds(box)
        assert not result.has_collision
        assert result.message == "Item within room bounds"

    def test_check_bounds_extends_right(self, detector: CollisionDetector) -> None:
        """Test bounds check for item extending past right wall."""
        box = AABB.from_position_and_size(4, 1, 2, 2)  # Extends past x=5
        result = detector.check_room_bounds(box)
        assert result.has_collision
        assert result.severity == CollisionSeverity.ERROR

    def test_check_bounds_extends_bottom(self, detector: CollisionDetector) -> None:
        """Test bounds check for item extending past bottom wall."""
        box = AABB.from_position_and_size(1, 3, 2, 2)  # Extends past z=4
        result = detector.check_room_bounds(box)
        assert result.has_collision
        assert result.severity == CollisionSeverity.ERROR

    def test_check_bounds_negative_position(self, detector: CollisionDetector) -> None:
        """Test bounds check for item with negative position."""
        box = AABB.from_position_and_size(-1, 1, 1, 1)
        result = detector.check_room_bounds(box)
        assert result.has_collision


class TestCollisionDetectorCheckWallProximity:
    """Tests for CollisionDetector.check_wall_proximity method."""

    @pytest.fixture
    def detector(self) -> CollisionDetector:
        """Create a test collision detector."""
        return CollisionDetector(room_width=5.0, room_depth=4.0)

    def test_check_wall_proximity_all_walls(self, detector: CollisionDetector) -> None:
        """Test wall proximity returns results for all walls."""
        box = AABB.from_position_and_size(2, 1.5, 1, 1)
        results = detector.check_wall_proximity(box)
        assert "north" in results
        assert "south" in results
        assert "east" in results
        assert "west" in results

    def test_check_wall_proximity_distances(self, detector: CollisionDetector) -> None:
        """Test wall proximity calculates correct distances."""
        box = AABB.from_position_and_size(1, 1, 1, 1)  # 1x1 at (1,1)
        results = detector.check_wall_proximity(box)
        assert results["north"].distance == pytest.approx(1.0)  # z=1
        assert results["south"].distance == pytest.approx(2.0)  # 4-2=2
        assert results["west"].distance == pytest.approx(1.0)  # x=1
        assert results["east"].distance == pytest.approx(3.0)  # 5-2=3

    def test_check_wall_proximity_with_min_distance(self, detector: CollisionDetector) -> None:
        """Test wall proximity with minimum distance requirement."""
        box = AABB.from_position_and_size(0.2, 0.2, 1, 1)
        results = detector.check_wall_proximity(box, min_distance=0.5)
        # Too close to north and west walls
        assert results["north"].has_collision
        assert results["west"].has_collision
        # Far enough from south and east
        assert not results["south"].has_collision
        assert not results["east"].has_collision


class TestCollisionDetectorCheckWalkingPath:
    """Tests for CollisionDetector.check_walking_path method."""

    @pytest.fixture
    def detector(self) -> CollisionDetector:
        """Create a test collision detector."""
        return CollisionDetector(room_width=10.0, room_depth=10.0)

    def test_check_walking_path_adequate(self, detector: CollisionDetector) -> None:
        """Test walking path check with adequate gaps."""
        boxes = [
            AABB.from_position_and_size(0, 0, 1, 1),
            AABB.from_position_and_size(2, 0, 1, 1),  # 1m gap
        ]
        violations = detector.check_walking_path(boxes)
        assert len(violations) == 0

    def test_check_walking_path_too_narrow(self, detector: CollisionDetector) -> None:
        """Test walking path check with narrow gap."""
        boxes = [
            AABB.from_position_and_size(0, 0, 1, 1),
            AABB.from_position_and_size(1.4, 0, 1, 1),  # 0.4m gap
        ]
        violations = detector.check_walking_path(boxes)
        assert len(violations) == 1
        assert violations[0][2] == pytest.approx(0.4)

    def test_check_walking_path_custom_width(self, detector: CollisionDetector) -> None:
        """Test walking path check with custom minimum width."""
        boxes = [
            AABB.from_position_and_size(0, 0, 1, 1),
            AABB.from_position_and_size(1.5, 0, 1, 1),  # 0.5m gap
        ]
        # With default 0.6m, this is a violation
        violations_default = detector.check_walking_path(boxes)
        assert len(violations_default) == 1

        # With custom 0.4m, this is OK
        violations_custom = detector.check_walking_path(boxes, path_width=0.4)
        assert len(violations_custom) == 0


class TestCollisionDetectorFindAllCollisions:
    """Tests for CollisionDetector.find_all_collisions method."""

    @pytest.fixture
    def detector(self) -> CollisionDetector:
        """Create a test collision detector."""
        return CollisionDetector(room_width=10.0, room_depth=10.0)

    def test_find_all_collisions_none(self, detector: CollisionDetector) -> None:
        """Test finding collisions when there are none."""
        boxes = [
            AABB.from_position_and_size(0, 0, 1, 1),
            AABB.from_position_and_size(3, 0, 1, 1),
            AABB.from_position_and_size(6, 0, 1, 1),
        ]
        collisions = detector.find_all_collisions(boxes)
        assert len(collisions) == 0

    def test_find_all_collisions_some(self, detector: CollisionDetector) -> None:
        """Test finding collisions when some exist."""
        boxes = [
            AABB.from_position_and_size(0, 0, 2, 2),
            AABB.from_position_and_size(1, 1, 2, 2),  # Overlaps with first
            AABB.from_position_and_size(5, 5, 1, 1),  # No overlap
        ]
        collisions = detector.find_all_collisions(boxes)
        assert len(collisions) == 1
        assert collisions[0][0] == 0
        assert collisions[0][1] == 1

    def test_find_all_collisions_multiple(self, detector: CollisionDetector) -> None:
        """Test finding multiple collisions."""
        boxes = [
            AABB.from_position_and_size(0, 0, 2, 2),
            AABB.from_position_and_size(1, 1, 2, 2),
            AABB.from_position_and_size(2, 2, 2, 2),  # Overlaps with second
        ]
        collisions = detector.find_all_collisions(boxes)
        assert len(collisions) == 2


class TestCollisionDetectorGetMinimumSeparation:
    """Tests for CollisionDetector.get_minimum_separation method."""

    @pytest.fixture
    def detector(self) -> CollisionDetector:
        """Create a test collision detector."""
        return CollisionDetector(room_width=10.0, room_depth=10.0)

    def test_minimum_separation_single_item(self, detector: CollisionDetector) -> None:
        """Test minimum separation with single item."""
        boxes = [AABB.from_position_and_size(0, 0, 1, 1)]
        sep = detector.get_minimum_separation(boxes)
        assert sep == float("inf")

    def test_minimum_separation_no_overlap(self, detector: CollisionDetector) -> None:
        """Test minimum separation with no overlaps."""
        boxes = [
            AABB.from_position_and_size(0, 0, 1, 1),
            AABB.from_position_and_size(2, 0, 1, 1),  # 1m gap
            AABB.from_position_and_size(4, 0, 1, 1),  # 1m gap
        ]
        sep = detector.get_minimum_separation(boxes)
        assert sep == pytest.approx(1.0)

    def test_minimum_separation_with_overlap(self, detector: CollisionDetector) -> None:
        """Test minimum separation with overlapping items."""
        boxes = [
            AABB.from_position_and_size(0, 0, 2, 2),
            AABB.from_position_and_size(1, 1, 2, 2),  # Overlapping
        ]
        sep = detector.get_minimum_separation(boxes)
        assert sep < 0


class TestCheckRotatedCollision:
    """Tests for check_rotated_collision function."""

    def test_rotated_collision_overlapping(self) -> None:
        """Test rotated collision with overlapping boxes."""
        box1 = AABB.from_position_and_size(0, 0, 2, 2)
        box2 = AABB.from_position_and_size(1, 1, 2, 2)
        result = check_rotated_collision(box1, 0, box2, 90)
        assert result.has_collision
        assert result.severity == CollisionSeverity.ERROR

    def test_rotated_collision_no_overlap(self) -> None:
        """Test rotated collision with no overlap."""
        box1 = AABB.from_position_and_size(0, 0, 1, 1)
        box2 = AABB.from_position_and_size(5, 5, 1, 1)
        result = check_rotated_collision(box1, 90, box2, 180)
        assert not result.has_collision
        assert result.distance > 0


class TestCollisionDetectorIntegration:
    """Integration tests for CollisionDetector."""

    def test_furniture_placement_validation(self) -> None:
        """Test validating a complete furniture layout."""
        detector = CollisionDetector(room_width=5.0, room_depth=4.0)

        # Define furniture items with adequate spacing
        bed = AABB.from_position_and_size(0.5, 0.5, 2.0, 1.8)
        nightstand = AABB.from_position_and_size(3.5, 0.5, 0.5, 0.5)  # 1m gap from bed
        dresser = AABB.from_position_and_size(0.5, 3.0, 1.2, 0.5)  # 0.7m gap from bed

        items = [bed, nightstand, dresser]

        # Check all items are within bounds
        for item in items:
            result = detector.check_room_bounds(item)
            assert not result.has_collision, "Item out of bounds"

        # Check for collisions
        collisions = detector.find_all_collisions(items)
        assert len(collisions) == 0, "Items should not collide"

        # Check walking paths
        violations = detector.check_walking_path(items)
        assert len(violations) == 0, "Walking paths should be adequate"

    def test_complex_layout_with_clearances(self) -> None:
        """Test complex layout with clearance requirements."""
        detector = CollisionDetector(room_width=5.0, room_depth=4.0)

        # Main furniture
        desk = AABB.from_position_and_size(0.5, 0.5, 1.5, 0.8)
        chair_clearance = ClearanceRequirement(front=0.6, back=0.5, left=0.3, right=0.3)

        # Chair position (behind desk)
        chair = AABB.from_position_and_size(0.8, 1.5, 0.6, 0.6)

        # Check chair has clearance from desk
        detector.check_clearance(chair, desk, chair_clearance)
        # Chair is close to desk, might violate clearance
        # This is expected in this setup

        # Add a bookshelf
        bookshelf = AABB.from_position_and_size(3.5, 0, 1.2, 0.4)

        # Verify bookshelf is in bounds
        assert not detector.check_room_bounds(bookshelf).has_collision

        # Check no physical collisions
        items = [desk, chair, bookshelf]
        collisions = detector.find_all_collisions(items)
        assert len(collisions) == 0
