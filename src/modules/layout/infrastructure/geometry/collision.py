"""Collision detection algorithms for feng shui layout generation."""

from dataclasses import dataclass
from enum import StrEnum
from typing import NamedTuple


class CollisionSeverity(StrEnum):
    """Severity levels for collision issues."""

    ERROR = "error"  # Furniture physically overlaps
    WARNING = "warning"  # Clearance violation
    INFO = "info"  # Recommendation (e.g., could be closer)


@dataclass(frozen=True)
class AABB:
    """Axis-Aligned Bounding Box.

    Represents a rectangular region in 2D space (top-down view).

    Attributes:
        min_x: Minimum X coordinate.
        min_z: Minimum Z coordinate.
        max_x: Maximum X coordinate.
        max_z: Maximum Z coordinate.
    """

    min_x: float
    min_z: float
    max_x: float
    max_z: float

    @property
    def width(self) -> float:
        """Get the width (X dimension)."""
        return self.max_x - self.min_x

    @property
    def depth(self) -> float:
        """Get the depth (Z dimension)."""
        return self.max_z - self.min_z

    @property
    def center_x(self) -> float:
        """Get the center X coordinate."""
        return (self.min_x + self.max_x) / 2

    @property
    def center_z(self) -> float:
        """Get the center Z coordinate."""
        return (self.min_z + self.max_z) / 2

    @property
    def area(self) -> float:
        """Get the area of the bounding box."""
        return self.width * self.depth

    def contains_point(self, x: float, z: float) -> bool:
        """Check if a point is inside the bounding box.

        Args:
            x: X coordinate.
            z: Z coordinate.

        Returns:
            True if the point is inside the box.
        """
        return self.min_x <= x <= self.max_x and self.min_z <= z <= self.max_z

    def intersects(self, other: "AABB") -> bool:
        """Check if this box intersects with another.

        Args:
            other: Another AABB to check against.

        Returns:
            True if the boxes overlap.
        """
        return not (
            self.max_x <= other.min_x
            or other.max_x <= self.min_x
            or self.max_z <= other.min_z
            or other.max_z <= self.min_z
        )

    def touches(self, other: "AABB") -> bool:
        """Check if this box touches (but doesn't overlap) another.

        Args:
            other: Another AABB to check against.

        Returns:
            True if the boxes are adjacent.
        """
        # Boxes touch if they share an edge but don't overlap
        if self.intersects(other):
            return False
        # Check if they share an edge
        x_adjacent = self.max_x == other.min_x or other.max_x == self.min_x
        z_adjacent = self.max_z == other.min_z or other.max_z == self.min_z
        x_overlap = not (self.max_x < other.min_x or other.max_x < self.min_x)
        z_overlap = not (self.max_z < other.min_z or other.max_z < self.min_z)
        return (x_adjacent and z_overlap) or (z_adjacent and x_overlap)

    def distance_to(self, other: "AABB") -> float:
        """Calculate the minimum distance between two boxes.

        Args:
            other: Another AABB.

        Returns:
            Minimum distance between the boxes (0 if overlapping or touching).
        """
        dx = max(0, max(self.min_x - other.max_x, other.min_x - self.max_x))
        dz = max(0, max(self.min_z - other.max_z, other.min_z - self.max_z))
        return (dx * dx + dz * dz) ** 0.5

    def expanded(self, amount: float) -> "AABB":
        """Create an expanded copy of this box.

        Args:
            amount: Amount to expand on each side.

        Returns:
            New AABB expanded by the given amount.
        """
        return AABB(
            min_x=self.min_x - amount,
            min_z=self.min_z - amount,
            max_x=self.max_x + amount,
            max_z=self.max_z + amount,
        )

    def intersection(self, other: "AABB") -> "AABB | None":
        """Get the intersection of two boxes.

        Args:
            other: Another AABB.

        Returns:
            AABB representing the intersection, or None if no intersection.
        """
        if not self.intersects(other):
            return None
        return AABB(
            min_x=max(self.min_x, other.min_x),
            min_z=max(self.min_z, other.min_z),
            max_x=min(self.max_x, other.max_x),
            max_z=min(self.max_z, other.max_z),
        )

    @classmethod
    def from_position_and_size(cls, x: float, z: float, width: float, depth: float) -> "AABB":
        """Create AABB from position and dimensions.

        Args:
            x: X position (left edge).
            z: Z position (top edge).
            width: Width in X direction.
            depth: Depth in Z direction.

        Returns:
            New AABB.
        """
        return cls(min_x=x, min_z=z, max_x=x + width, max_z=z + depth)

    @classmethod
    def from_center_and_size(
        cls, center_x: float, center_z: float, width: float, depth: float
    ) -> "AABB":
        """Create AABB from center point and dimensions.

        Args:
            center_x: Center X coordinate.
            center_z: Center Z coordinate.
            width: Width in X direction.
            depth: Depth in Z direction.

        Returns:
            New AABB.
        """
        half_w = width / 2
        half_d = depth / 2
        return cls(
            min_x=center_x - half_w,
            min_z=center_z - half_d,
            max_x=center_x + half_w,
            max_z=center_z + half_d,
        )


class CollisionResult(NamedTuple):
    """Result of a collision check between two items.

    Attributes:
        has_collision: Whether there is a collision or issue.
        severity: Severity of the collision.
        overlap_area: Area of overlap if any.
        distance: Distance between items (negative if overlapping).
        message: Human-readable description.
    """

    has_collision: bool
    severity: CollisionSeverity
    overlap_area: float
    distance: float
    message: str


@dataclass(frozen=True)
class ClearanceRequirement:
    """Clearance requirements for furniture.

    Attributes:
        front: Required clearance in front (direction of use).
        back: Required clearance behind.
        left: Required clearance on left side.
        right: Required clearance on right side.
    """

    front: float = 0.6  # 60cm default minimum clearance
    back: float = 0.0
    left: float = 0.3
    right: float = 0.3

    @classmethod
    def standard(cls) -> "ClearanceRequirement":
        """Create standard clearance requirements (60cm all sides)."""
        return cls(front=0.6, back=0.1, left=0.3, right=0.3)

    @classmethod
    def traffic_path(cls) -> "ClearanceRequirement":
        """Create clearance for traffic paths (90cm minimum)."""
        return cls(front=0.9, back=0.9, left=0.9, right=0.9)

    @classmethod
    def none(cls) -> "ClearanceRequirement":
        """Create no clearance requirements (for wall-mounted items)."""
        return cls(front=0.0, back=0.0, left=0.0, right=0.0)


class CollisionDetector:
    """Detects collisions between furniture items and room elements.

    Provides methods for:
    - AABB collision detection
    - Clearance zone checking
    - Wall proximity checking
    - Room boundary validation
    """

    # Minimum walking path width
    MIN_WALKING_PATH = 0.6  # 60cm

    # Minimum door clearance
    MIN_DOOR_CLEARANCE = 0.9  # 90cm

    def __init__(self, room_width: float, room_depth: float) -> None:
        """Initialize the collision detector.

        Args:
            room_width: Room width in meters.
            room_depth: Room depth in meters.
        """
        if room_width <= 0 or room_depth <= 0:
            raise ValueError("Room dimensions must be positive")
        self.room_width = room_width
        self.room_depth = room_depth
        self.room_bounds = AABB(min_x=0, min_z=0, max_x=room_width, max_z=room_depth)

    def check_collision(self, box1: AABB, box2: AABB) -> CollisionResult:
        """Check for collision between two bounding boxes.

        Args:
            box1: First bounding box.
            box2: Second bounding box.

        Returns:
            CollisionResult with collision details.
        """
        if box1.intersects(box2):
            intersection = box1.intersection(box2)
            overlap_area = intersection.area if intersection else 0
            return CollisionResult(
                has_collision=True,
                severity=CollisionSeverity.ERROR,
                overlap_area=overlap_area,
                distance=-(overlap_area**0.5),  # Negative distance for overlap
                message=f"Items overlap with area {overlap_area:.3f}m²",
            )

        distance = box1.distance_to(box2)
        return CollisionResult(
            has_collision=False,
            severity=CollisionSeverity.INFO,
            overlap_area=0,
            distance=distance,
            message=f"No collision, distance: {distance:.2f}m",
        )

    def check_clearance(
        self,
        item_box: AABB,
        other_box: AABB,
        clearance: ClearanceRequirement,
        rotation: int = 0,
    ) -> CollisionResult:
        """Check if clearance requirements are met.

        Args:
            item_box: Bounding box of the item needing clearance.
            other_box: Bounding box of the other item.
            clearance: Clearance requirements.
            rotation: Item rotation in degrees (0, 90, 180, 270).

        Returns:
            CollisionResult with clearance check details.
        """
        # Adjust clearance based on rotation
        front, back, left, right = self._rotate_clearance(clearance, rotation)

        # Expand item box by clearance amounts
        expanded = AABB(
            min_x=item_box.min_x - left,
            min_z=item_box.min_z - back,
            max_x=item_box.max_x + right,
            max_z=item_box.max_z + front,
        )

        if expanded.intersects(other_box):
            distance = item_box.distance_to(other_box)
            return CollisionResult(
                has_collision=True,
                severity=CollisionSeverity.WARNING,
                overlap_area=0,
                distance=distance,
                message=f"Clearance violated, distance: {distance:.2f}m",
            )

        distance = item_box.distance_to(other_box)
        return CollisionResult(
            has_collision=False,
            severity=CollisionSeverity.INFO,
            overlap_area=0,
            distance=distance,
            message=f"Clearance OK, distance: {distance:.2f}m",
        )

    def check_room_bounds(self, box: AABB) -> CollisionResult:
        """Check if an item is within room bounds.

        Args:
            box: Bounding box of the item.

        Returns:
            CollisionResult with boundary check details.
        """
        if (
            box.min_x < 0
            or box.min_z < 0
            or box.max_x > self.room_width
            or box.max_z > self.room_depth
        ):
            # Calculate how far outside
            overflow_x = max(0, max(-box.min_x, box.max_x - self.room_width))
            overflow_z = max(0, max(-box.min_z, box.max_z - self.room_depth))
            overflow = max(overflow_x, overflow_z)
            return CollisionResult(
                has_collision=True,
                severity=CollisionSeverity.ERROR,
                overlap_area=overflow_x * overflow_z if overflow_x and overflow_z else 0,
                distance=-overflow,
                message=f"Item extends {overflow:.2f}m outside room bounds",
            )

        return CollisionResult(
            has_collision=False,
            severity=CollisionSeverity.INFO,
            overlap_area=0,
            distance=min(
                box.min_x,
                box.min_z,
                self.room_width - box.max_x,
                self.room_depth - box.max_z,
            ),
            message="Item within room bounds",
        )

    def check_wall_proximity(
        self, box: AABB, min_distance: float = 0.0
    ) -> dict[str, CollisionResult]:
        """Check proximity to walls.

        Args:
            box: Bounding box of the item.
            min_distance: Minimum required distance from walls.

        Returns:
            Dict with results for each wall (north, south, east, west).
        """
        results = {}

        # North wall (z=0)
        dist_north = box.min_z
        results["north"] = self._wall_result("north", dist_north, min_distance)

        # South wall (z=room_depth)
        dist_south = self.room_depth - box.max_z
        results["south"] = self._wall_result("south", dist_south, min_distance)

        # West wall (x=0)
        dist_west = box.min_x
        results["west"] = self._wall_result("west", dist_west, min_distance)

        # East wall (x=room_width)
        dist_east = self.room_width - box.max_x
        results["east"] = self._wall_result("east", dist_east, min_distance)

        return results

    def check_walking_path(
        self, boxes: list[AABB], path_width: float | None = None
    ) -> list[tuple[AABB, AABB, float]]:
        """Check if walking paths between items are adequate.

        Args:
            boxes: List of all item bounding boxes.
            path_width: Minimum path width (defaults to MIN_WALKING_PATH).

        Returns:
            List of tuples (box1, box2, gap) for pairs with insufficient paths.
        """
        if path_width is None:
            path_width = self.MIN_WALKING_PATH

        violations = []
        for i, box1 in enumerate(boxes):
            for box2 in boxes[i + 1 :]:
                distance = box1.distance_to(box2)
                if 0 < distance < path_width:
                    violations.append((box1, box2, distance))

        return violations

    def find_all_collisions(self, boxes: list[AABB]) -> list[tuple[int, int, CollisionResult]]:
        """Find all collisions between a list of items.

        Args:
            boxes: List of all item bounding boxes.

        Returns:
            List of tuples (index1, index2, result) for all collisions.
        """
        collisions = []
        for i, box1 in enumerate(boxes):
            for j, box2 in enumerate(boxes[i + 1 :], start=i + 1):
                result = self.check_collision(box1, box2)
                if result.has_collision:
                    collisions.append((i, j, result))
        return collisions

    def get_minimum_separation(self, boxes: list[AABB]) -> float:
        """Get the minimum separation between any two items.

        Args:
            boxes: List of all item bounding boxes.

        Returns:
            Minimum distance (negative if overlapping).
        """
        if len(boxes) < 2:
            return float("inf")

        min_distance = float("inf")
        for i, box1 in enumerate(boxes):
            for box2 in boxes[i + 1 :]:
                result = self.check_collision(box1, box2)
                if result.has_collision:
                    min_distance = min(min_distance, result.distance)
                else:
                    min_distance = min(min_distance, result.distance)

        return min_distance

    def _rotate_clearance(
        self, clearance: ClearanceRequirement, rotation: int
    ) -> tuple[float, float, float, float]:
        """Rotate clearance requirements based on item rotation.

        Args:
            clearance: Original clearance requirements.
            rotation: Rotation in degrees.

        Returns:
            Tuple of (front, back, left, right) after rotation.
        """
        rotation = rotation % 360
        if rotation == 0:
            return clearance.front, clearance.back, clearance.left, clearance.right
        if rotation == 90:
            return clearance.left, clearance.right, clearance.back, clearance.front
        if rotation == 180:
            return clearance.back, clearance.front, clearance.right, clearance.left
        if rotation == 270:
            return clearance.right, clearance.left, clearance.front, clearance.back
        # Default for other rotations
        return clearance.front, clearance.back, clearance.left, clearance.right

    def _wall_result(self, wall: str, distance: float, min_distance: float) -> CollisionResult:
        """Create a wall proximity result.

        Args:
            wall: Wall name.
            distance: Distance to wall.
            min_distance: Minimum required distance.

        Returns:
            CollisionResult for wall proximity.
        """
        if distance < 0:
            return CollisionResult(
                has_collision=True,
                severity=CollisionSeverity.ERROR,
                overlap_area=abs(distance),
                distance=distance,
                message=f"Item extends {abs(distance):.2f}m beyond {wall} wall",
            )
        if distance < min_distance:
            return CollisionResult(
                has_collision=True,
                severity=CollisionSeverity.WARNING,
                overlap_area=0,
                distance=distance,
                message=f"Item too close to {wall} wall: {distance:.2f}m",
            )
        return CollisionResult(
            has_collision=False,
            severity=CollisionSeverity.INFO,
            overlap_area=0,
            distance=distance,
            message=f"Distance to {wall} wall: {distance:.2f}m",
        )


def check_rotated_collision(
    box1: AABB,
    rotation1: int,
    box2: AABB,
    rotation2: int,
) -> CollisionResult:
    """Check collision considering rotations.

    Note: This simplified version assumes rotation is already applied
    to the bounding box dimensions. For actual rotated collisions,
    you would need to swap width/depth based on rotation.

    Args:
        box1: First item's bounding box (already adjusted for rotation).
        rotation1: First item's rotation (for reference).
        box2: Second item's bounding box (already adjusted for rotation).
        rotation2: Second item's rotation (for reference).

    Returns:
        CollisionResult with collision details.
    """
    # For AABB collision, rotation is already factored into dimensions
    # This function exists for future extension to OBB collision
    if box1.intersects(box2):
        intersection = box1.intersection(box2)
        overlap_area = intersection.area if intersection else 0
        return CollisionResult(
            has_collision=True,
            severity=CollisionSeverity.ERROR,
            overlap_area=overlap_area,
            distance=-(overlap_area**0.5),
            message=f"Rotated items collide with overlap {overlap_area:.3f}m²",
        )

    distance = box1.distance_to(box2)
    return CollisionResult(
        has_collision=False,
        severity=CollisionSeverity.INFO,
        overlap_area=0,
        distance=distance,
        message=f"No collision between rotated items, distance: {distance:.2f}m",
    )
