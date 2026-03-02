"""Placement entity for feng shui layout."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from src.modules.layout.domain.value_objects.coordinates import (
    BoundingBox,
    Position3D,
    Rotation,
)

if TYPE_CHECKING:
    from src.modules.layout.domain.entities.furniture import Furniture


@dataclass
class Placement:
    """A furniture item placed in the room.

    Attributes:
        furniture: The furniture being placed.
        position: Center position on floor (x, y=0, z).
        rotation: Rotation angle in degrees.
        is_essential: Whether this placement is essential.
        feng_shui_notes: Notes about feng shui considerations.
        scale: Scale factor (1.0 = original size).
    """

    furniture: Furniture
    position: Position3D
    rotation: Rotation = Rotation.DEG_0
    is_essential: bool = True
    feng_shui_notes: list[str] = field(default_factory=list)
    scale: float = 1.0

    def __post_init__(self) -> None:
        """Validate placement properties."""
        if self.scale <= 0 or self.scale > 1.0:
            msg = f"scale must be between 0 and 1.0, got {self.scale}"
            raise ValueError(msg)

    @property
    def effective_width(self) -> float:
        """Get effective width after rotation and scaling."""
        base_width = self.furniture.dimensions.width * self.scale
        base_depth = self.furniture.dimensions.depth * self.scale

        if self.rotation in (Rotation.DEG_0, Rotation.DEG_180):
            return base_width
        return base_depth

    @property
    def effective_depth(self) -> float:
        """Get effective depth after rotation and scaling."""
        base_width = self.furniture.dimensions.width * self.scale
        base_depth = self.furniture.dimensions.depth * self.scale

        if self.rotation in (Rotation.DEG_0, Rotation.DEG_180):
            return base_depth
        return base_width

    @property
    def effective_height(self) -> float:
        """Get effective height after scaling."""
        return self.furniture.dimensions.height * self.scale

    def get_bounding_box(self) -> BoundingBox:
        """Get bounding box for this placement.

        Returns:
            BoundingBox accounting for position, rotation, and scale.
        """
        half_width = self.effective_width / 2
        half_depth = self.effective_depth / 2

        return BoundingBox(
            min_x=self.position.x - half_width,
            min_y=self.position.y,
            min_z=self.position.z - half_depth,
            max_x=self.position.x + half_width,
            max_y=self.position.y + self.effective_height,
            max_z=self.position.z + half_depth,
        )

    def get_clearance_box(self) -> BoundingBox:
        """Get bounding box including clearance zone.

        Returns:
            BoundingBox expanded by furniture's min_clearance.
        """
        return self.get_bounding_box().expand(self.furniture.min_clearance)

    def collides_with(self, other: Placement) -> bool:
        """Check if this placement collides with another.

        Args:
            other: Another placement to check.

        Returns:
            True if placements overlap (on floor plane).
        """
        return self.get_bounding_box().intersects_2d(other.get_bounding_box())

    def collides_with_box(self, box: BoundingBox) -> bool:
        """Check if this placement collides with a bounding box.

        Args:
            box: Bounding box to check (e.g., door swing area).

        Returns:
            True if placement overlaps with box.
        """
        return self.get_bounding_box().intersects_2d(box)

    def is_in_bounds(self, room_width: float, room_depth: float) -> bool:
        """Check if placement is fully within room bounds.

        Args:
            room_width: Room width in meters.
            room_depth: Room depth in meters.

        Returns:
            True if entire furniture is within room.
        """
        bbox = self.get_bounding_box()
        return (
            bbox.min_x >= 0
            and bbox.max_x <= room_width
            and bbox.min_z >= 0
            and bbox.max_z <= room_depth
        )

    def distance_to(self, other: Placement) -> float:
        """Calculate distance to another placement (center to center).

        Args:
            other: Another placement.

        Returns:
            Distance in meters.
        """
        return self.position.distance_2d(other.position)

    def distance_to_point(self, point: Position3D) -> float:
        """Calculate distance to a point.

        Args:
            point: Target point.

        Returns:
            Distance in meters (on floor plane).
        """
        return self.position.distance_2d(point)

    def faces_position(self, target: Position3D, tolerance: float = 45.0) -> bool:
        """Check if furniture faces a target position.

        Args:
            target: Position to check (e.g., door).
            tolerance: Angle tolerance in degrees.

        Returns:
            True if furniture's front faces the target within tolerance.
        """
        # Calculate angle to target
        dx = target.x - self.position.x
        dz = target.z - self.position.z
        angle_to_target = math.degrees(math.atan2(dx, dz))

        # Normalize angles to 0-360
        angle_to_target = angle_to_target % 360
        furniture_facing = float(self.rotation)

        # Check if facing is within tolerance
        diff = abs(angle_to_target - furniture_facing)
        if diff > 180:
            diff = 360 - diff

        return diff <= tolerance

    def is_against_wall(self, room_width: float, room_depth: float, tolerance: float = 0.1) -> bool:
        """Check if furniture is placed against a wall.

        Args:
            room_width: Room width in meters.
            room_depth: Room depth in meters.
            tolerance: Distance tolerance in meters.

        Returns:
            True if furniture is against at least one wall.
        """
        bbox = self.get_bounding_box()
        return (
            bbox.min_x <= tolerance
            or bbox.max_x >= room_width - tolerance
            or bbox.min_z <= tolerance
            or bbox.max_z >= room_depth - tolerance
        )

    def with_rotation(self, rotation: Rotation) -> Placement:
        """Create new placement with different rotation.

        Args:
            rotation: New rotation angle.

        Returns:
            New Placement with updated rotation.
        """
        return Placement(
            furniture=self.furniture,
            position=self.position,
            rotation=rotation,
            is_essential=self.is_essential,
            feng_shui_notes=self.feng_shui_notes.copy(),
            scale=self.scale,
        )

    def with_position(self, position: Position3D) -> Placement:
        """Create new placement with different position.

        Args:
            position: New position.

        Returns:
            New Placement with updated position.
        """
        return Placement(
            furniture=self.furniture,
            position=position,
            rotation=self.rotation,
            is_essential=self.is_essential,
            feng_shui_notes=self.feng_shui_notes.copy(),
            scale=self.scale,
        )

    def with_scale(self, scale: float) -> Placement:
        """Create new placement with different scale.

        Args:
            scale: New scale factor (0-1.0).

        Returns:
            New Placement with updated scale.
        """
        return Placement(
            furniture=self.furniture,
            position=self.position,
            rotation=self.rotation,
            is_essential=self.is_essential,
            feng_shui_notes=self.feng_shui_notes.copy(),
            scale=scale,
        )

    def add_feng_shui_note(self, note: str) -> None:
        """Add a feng shui note to this placement.

        Args:
            note: Note about feng shui consideration.
        """
        self.feng_shui_notes.append(note)
