"""Coordinate and spatial value objects for feng shui layout."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


class Rotation(IntEnum):
    """Valid rotation angles in degrees."""

    DEG_0 = 0
    DEG_90 = 90
    DEG_180 = 180
    DEG_270 = 270

    @classmethod
    def from_degrees(cls, degrees: float) -> Rotation:
        """Convert degrees to nearest valid rotation.

        Args:
            degrees: Rotation in degrees (0-360).

        Returns:
            Nearest valid Rotation enum value.
        """
        normalized = int(degrees) % 360
        if normalized < 45:
            return cls.DEG_0
        if normalized < 135:
            return cls.DEG_90
        if normalized < 225:
            return cls.DEG_180
        if normalized < 315:
            return cls.DEG_270
        return cls.DEG_0


@dataclass(frozen=True)
class Position3D:
    """Immutable 3D position in meters.

    Coordinate system:
    - x: Width axis (left/right)
    - y: Height axis (up/down)
    - z: Depth axis (front/back)
    """

    x: float
    y: float
    z: float

    def __post_init__(self) -> None:
        """Validate coordinates are finite numbers."""
        for coord, name in [(self.x, "x"), (self.y, "y"), (self.z, "z")]:
            if not isinstance(coord, (int, float)):
                msg = f"{name} must be a number, got {type(coord)}"
                raise TypeError(msg)

    def distance_to(self, other: Position3D) -> float:
        """Calculate Euclidean distance to another position.

        Args:
            other: Target position.

        Returns:
            Distance in meters.
        """
        return (
            (self.x - other.x) ** 2 + (self.y - other.y) ** 2 + (self.z - other.z) ** 2
        ) ** 0.5

    def distance_2d(self, other: Position3D) -> float:
        """Calculate 2D distance (ignoring height) to another position.

        Args:
            other: Target position.

        Returns:
            Distance in meters on the floor plane (x-z).
        """
        return ((self.x - other.x) ** 2 + (self.z - other.z) ** 2) ** 0.5

    def translate(self, dx: float = 0, dy: float = 0, dz: float = 0) -> Position3D:
        """Create new position translated by given offsets.

        Args:
            dx: X offset in meters.
            dy: Y offset in meters.
            dz: Z offset in meters.

        Returns:
            New Position3D with applied translation.
        """
        return Position3D(x=self.x + dx, y=self.y + dy, z=self.z + dz)

    @classmethod
    def origin(cls) -> Position3D:
        """Create position at origin (0, 0, 0)."""
        return cls(x=0.0, y=0.0, z=0.0)


@dataclass(frozen=True)
class BoundingBox:
    """Axis-aligned bounding box for collision detection.

    Defined by minimum and maximum corners.
    """

    min_x: float
    min_y: float
    min_z: float
    max_x: float
    max_y: float
    max_z: float

    def __post_init__(self) -> None:
        """Validate bounding box dimensions."""
        if self.min_x > self.max_x:
            msg = f"min_x ({self.min_x}) must be <= max_x ({self.max_x})"
            raise ValueError(msg)
        if self.min_y > self.max_y:
            msg = f"min_y ({self.min_y}) must be <= max_y ({self.max_y})"
            raise ValueError(msg)
        if self.min_z > self.max_z:
            msg = f"min_z ({self.min_z}) must be <= max_z ({self.max_z})"
            raise ValueError(msg)

    @property
    def width(self) -> float:
        """Width of bounding box (x-axis)."""
        return self.max_x - self.min_x

    @property
    def height(self) -> float:
        """Height of bounding box (y-axis)."""
        return self.max_y - self.min_y

    @property
    def depth(self) -> float:
        """Depth of bounding box (z-axis)."""
        return self.max_z - self.min_z

    @property
    def center(self) -> Position3D:
        """Center point of bounding box."""
        return Position3D(
            x=(self.min_x + self.max_x) / 2,
            y=(self.min_y + self.max_y) / 2,
            z=(self.min_z + self.max_z) / 2,
        )

    @property
    def floor_area(self) -> float:
        """Floor area of bounding box (width x depth)."""
        return self.width * self.depth

    @property
    def volume(self) -> float:
        """Volume of bounding box."""
        return self.width * self.height * self.depth

    def intersects(self, other: BoundingBox) -> bool:
        """Check if this bounding box intersects with another.

        Args:
            other: Another bounding box.

        Returns:
            True if boxes intersect (including touching).
        """
        return (
            self.min_x <= other.max_x
            and self.max_x >= other.min_x
            and self.min_y <= other.max_y
            and self.max_y >= other.min_y
            and self.min_z <= other.max_z
            and self.max_z >= other.min_z
        )

    def intersects_2d(self, other: BoundingBox) -> bool:
        """Check if boxes intersect on the floor plane (ignoring height).

        Args:
            other: Another bounding box.

        Returns:
            True if boxes intersect on x-z plane.
        """
        return (
            self.min_x <= other.max_x
            and self.max_x >= other.min_x
            and self.min_z <= other.max_z
            and self.max_z >= other.min_z
        )

    def contains_point(self, point: Position3D) -> bool:
        """Check if point is inside this bounding box.

        Args:
            point: Position to check.

        Returns:
            True if point is inside or on boundary.
        """
        return (
            self.min_x <= point.x <= self.max_x
            and self.min_y <= point.y <= self.max_y
            and self.min_z <= point.z <= self.max_z
        )

    def expand(self, margin: float) -> BoundingBox:
        """Create new bounding box expanded by margin on all sides.

        Args:
            margin: Distance to expand in meters.

        Returns:
            New expanded BoundingBox.
        """
        return BoundingBox(
            min_x=self.min_x - margin,
            min_y=self.min_y - margin,
            min_z=self.min_z - margin,
            max_x=self.max_x + margin,
            max_y=self.max_y + margin,
            max_z=self.max_z + margin,
        )

    @classmethod
    def from_center_and_size(
        cls,
        center: Position3D,
        width: float,
        height: float,
        depth: float,
    ) -> BoundingBox:
        """Create bounding box from center point and dimensions.

        Args:
            center: Center position.
            width: Width (x-axis).
            height: Height (y-axis).
            depth: Depth (z-axis).

        Returns:
            New BoundingBox.
        """
        half_w = width / 2
        half_h = height / 2
        half_d = depth / 2
        return cls(
            min_x=center.x - half_w,
            min_y=center.y - half_h,
            min_z=center.z - half_d,
            max_x=center.x + half_w,
            max_y=center.y + half_h,
            max_z=center.z + half_d,
        )

    @classmethod
    def from_position_and_size(
        cls,
        position: Position3D,
        width: float,
        height: float,
        depth: float,
    ) -> BoundingBox:
        """Create bounding box from corner position and dimensions.

        Position is treated as the minimum corner (bottom-left-front).

        Args:
            position: Minimum corner position.
            width: Width (x-axis).
            height: Height (y-axis).
            depth: Depth (z-axis).

        Returns:
            New BoundingBox.
        """
        return cls(
            min_x=position.x,
            min_y=position.y,
            min_z=position.z,
            max_x=position.x + width,
            max_y=position.y + height,
            max_z=position.z + depth,
        )
