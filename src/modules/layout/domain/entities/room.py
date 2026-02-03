"""Room entity for feng shui layout."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

from src.modules.layout.domain.value_objects.coordinates import BoundingBox, Position3D

if TYPE_CHECKING:
    from src.modules.layout.domain.entities.placement import Placement


class RoomType(str, Enum):
    """Supported room types for feng shui analysis."""

    BEDROOM = "bedroom"
    LIVING_ROOM = "living_room"
    OFFICE = "office"
    DINING_ROOM = "dining_room"
    KITCHEN = "kitchen"
    BATHROOM = "bathroom"

    @property
    def essential_furniture(self) -> list[str]:
        """Get essential furniture categories for this room type."""
        essentials = {
            self.BEDROOM: ["bed", "wardrobe"],
            self.LIVING_ROOM: ["sofa", "coffee_table"],
            self.OFFICE: ["desk", "chair"],
            self.DINING_ROOM: ["dining_table", "dining_chair"],
            self.KITCHEN: ["cabinet", "counter"],
            self.BATHROOM: ["toilet", "sink"],
        }
        return essentials.get(self, [])


class WallSide(str, Enum):
    """Wall sides for positioning doors and windows."""

    NORTH = "north"
    SOUTH = "south"
    EAST = "east"
    WEST = "west"

    @property
    def opposite(self) -> WallSide:
        """Get the opposite wall side."""
        opposites = {
            self.NORTH: self.SOUTH,
            self.SOUTH: self.NORTH,
            self.EAST: self.WEST,
            self.WEST: self.EAST,
        }
        return opposites[self]

    @property
    def is_horizontal(self) -> bool:
        """Check if wall runs horizontally (north/south walls)."""
        return self in (self.NORTH, self.SOUTH)


@dataclass
class DoorPosition:
    """Door position and properties.

    Attributes:
        wall: Wall side where door is located.
        offset: Distance from wall start in meters.
        width: Door width in meters.
        swing_inward: Whether door swings inward.
    """

    wall: WallSide
    offset: float
    width: float = 0.9
    swing_inward: bool = True

    def __post_init__(self) -> None:
        """Validate door properties."""
        if self.offset < 0:
            msg = f"Door offset must be >= 0, got {self.offset}"
            raise ValueError(msg)
        if self.width <= 0:
            msg = f"Door width must be > 0, got {self.width}"
            raise ValueError(msg)

    def get_swing_area(self, room_width: float, room_depth: float) -> BoundingBox:
        """Calculate the door swing area (90 degree arc approximated as box).

        Args:
            room_width: Room width (x-axis) in meters.
            room_depth: Room depth (z-axis) in meters.

        Returns:
            BoundingBox representing the swing area.
        """
        swing_radius = self.width

        if self.wall == WallSide.NORTH:
            # Door on north wall, swings toward south (negative z)
            z_pos = room_depth if self.swing_inward else room_depth
            return BoundingBox(
                min_x=self.offset,
                min_y=0,
                min_z=z_pos - swing_radius if self.swing_inward else z_pos,
                max_x=self.offset + self.width,
                max_y=2.1,
                max_z=z_pos if self.swing_inward else z_pos + swing_radius,
            )
        if self.wall == WallSide.SOUTH:
            # Door on south wall, swings toward north (positive z)
            return BoundingBox(
                min_x=self.offset,
                min_y=0,
                min_z=0 if self.swing_inward else -swing_radius,
                max_x=self.offset + self.width,
                max_y=2.1,
                max_z=swing_radius if self.swing_inward else 0,
            )
        if self.wall == WallSide.EAST:
            # Door on east wall, swings toward west (negative x)
            x_pos = room_width
            return BoundingBox(
                min_x=x_pos - swing_radius if self.swing_inward else x_pos,
                min_y=0,
                min_z=self.offset,
                max_x=x_pos if self.swing_inward else x_pos + swing_radius,
                max_y=2.1,
                max_z=self.offset + self.width,
            )
        # WallSide.WEST
        return BoundingBox(
            min_x=0 if self.swing_inward else -swing_radius,
            min_y=0,
            min_z=self.offset,
            max_x=swing_radius if self.swing_inward else 0,
            max_y=2.1,
            max_z=self.offset + self.width,
        )


@dataclass
class WindowPosition:
    """Window position and properties.

    Attributes:
        wall: Wall side where window is located.
        offset: Distance from wall start in meters.
        width: Window width in meters.
        height: Window height in meters.
        sill_height: Height from floor to window sill.
    """

    wall: WallSide
    offset: float
    width: float
    height: float = 1.2
    sill_height: float = 0.9

    def __post_init__(self) -> None:
        """Validate window properties."""
        if self.offset < 0:
            msg = f"Window offset must be >= 0, got {self.offset}"
            raise ValueError(msg)
        if self.width <= 0:
            msg = f"Window width must be > 0, got {self.width}"
            raise ValueError(msg)
        if self.height <= 0:
            msg = f"Window height must be > 0, got {self.height}"
            raise ValueError(msg)

    def get_natural_light_zone(
        self, room_width: float, room_depth: float, depth: float = 2.0
    ) -> BoundingBox:
        """Calculate the natural light zone extending from window.

        Args:
            room_width: Room width (x-axis) in meters.
            room_depth: Room depth (z-axis) in meters.
            depth: How far light extends into room (default 2m).

        Returns:
            BoundingBox representing the light zone.
        """
        if self.wall == WallSide.NORTH:
            return BoundingBox(
                min_x=max(0, self.offset - 0.5),
                min_y=0,
                min_z=room_depth - depth,
                max_x=min(room_width, self.offset + self.width + 0.5),
                max_y=2.5,
                max_z=room_depth,
            )
        if self.wall == WallSide.SOUTH:
            return BoundingBox(
                min_x=max(0, self.offset - 0.5),
                min_y=0,
                min_z=0,
                max_x=min(room_width, self.offset + self.width + 0.5),
                max_y=2.5,
                max_z=depth,
            )
        if self.wall == WallSide.EAST:
            return BoundingBox(
                min_x=room_width - depth,
                min_y=0,
                min_z=max(0, self.offset - 0.5),
                max_x=room_width,
                max_y=2.5,
                max_z=min(room_depth, self.offset + self.width + 0.5),
            )
        # WallSide.WEST
        return BoundingBox(
            min_x=0,
            min_y=0,
            min_z=max(0, self.offset - 0.5),
            max_x=depth,
            max_y=2.5,
            max_z=min(room_depth, self.offset + self.width + 0.5),
        )


@dataclass
class Room:
    """Room entity representing the physical space.

    Attributes:
        width: Room width (x-axis) in meters.
        depth: Room depth (z-axis) in meters.
        height: Room height (y-axis) in meters.
        room_type: Type of room (bedroom, office, etc.).
        doors: List of door positions.
        windows: List of window positions.
        direction: Room's facing direction (for feng shui).
    """

    width: float
    depth: float
    height: float = 2.8
    room_type: RoomType = RoomType.BEDROOM
    doors: list[DoorPosition] = field(default_factory=list)
    windows: list[WindowPosition] = field(default_factory=list)
    direction: WallSide = WallSide.NORTH
    _placements: list[Placement] = field(default_factory=list, repr=False)

    def __post_init__(self) -> None:
        """Validate room dimensions."""
        if self.width <= 0:
            msg = f"Room width must be > 0, got {self.width}"
            raise ValueError(msg)
        if self.depth <= 0:
            msg = f"Room depth must be > 0, got {self.depth}"
            raise ValueError(msg)
        if self.height <= 0:
            msg = f"Room height must be > 0, got {self.height}"
            raise ValueError(msg)

    @property
    def floor_area(self) -> float:
        """Calculate floor area in square meters."""
        return self.width * self.depth

    @property
    def volume(self) -> float:
        """Calculate room volume in cubic meters."""
        return self.width * self.depth * self.height

    @property
    def bounding_box(self) -> BoundingBox:
        """Get room bounding box."""
        return BoundingBox(
            min_x=0,
            min_y=0,
            min_z=0,
            max_x=self.width,
            max_y=self.height,
            max_z=self.depth,
        )

    @property
    def center(self) -> Position3D:
        """Get room center point."""
        return Position3D(x=self.width / 2, y=self.height / 2, z=self.depth / 2)

    @property
    def floor_center(self) -> Position3D:
        """Get center point on the floor."""
        return Position3D(x=self.width / 2, y=0, z=self.depth / 2)

    def get_command_position(self) -> Position3D:
        """Get the feng shui command position.

        The command position is the spot diagonally opposite from the
        main door, with a solid wall behind and clear view of the door.
        """
        if not self.doors:
            # Default to corner opposite of north wall
            return Position3D(x=self.width * 0.85, y=0, z=self.depth * 0.85)

        main_door = self.doors[0]

        # Position should be diagonally opposite from door
        if main_door.wall == WallSide.SOUTH:
            return Position3D(
                x=self.width - main_door.offset - main_door.width / 2,
                y=0,
                z=self.depth * 0.85,
            )
        if main_door.wall == WallSide.NORTH:
            return Position3D(
                x=self.width - main_door.offset - main_door.width / 2,
                y=0,
                z=self.depth * 0.15,
            )
        if main_door.wall == WallSide.WEST:
            return Position3D(
                x=self.width * 0.85,
                y=0,
                z=self.depth - main_door.offset - main_door.width / 2,
            )
        # WallSide.EAST
        return Position3D(
            x=self.width * 0.15,
            y=0,
            z=self.depth - main_door.offset - main_door.width / 2,
        )

    def get_wealth_corner(self) -> Position3D:
        """Get the feng shui wealth corner position.

        The wealth corner is diagonally opposite from the main entrance.
        """
        if not self.doors:
            return Position3D(x=self.width * 0.9, y=0, z=self.depth * 0.9)

        main_door = self.doors[0]

        if main_door.wall == WallSide.SOUTH:
            # Door on south, wealth corner in far north corner
            if main_door.offset < self.width / 2:
                return Position3D(x=self.width * 0.9, y=0, z=self.depth * 0.9)
            return Position3D(x=self.width * 0.1, y=0, z=self.depth * 0.9)
        if main_door.wall == WallSide.NORTH:
            if main_door.offset < self.width / 2:
                return Position3D(x=self.width * 0.9, y=0, z=self.depth * 0.1)
            return Position3D(x=self.width * 0.1, y=0, z=self.depth * 0.1)
        if main_door.wall == WallSide.WEST:
            if main_door.offset < self.depth / 2:
                return Position3D(x=self.width * 0.9, y=0, z=self.depth * 0.9)
            return Position3D(x=self.width * 0.9, y=0, z=self.depth * 0.1)
        # WallSide.EAST
        if main_door.offset < self.depth / 2:
            return Position3D(x=self.width * 0.1, y=0, z=self.depth * 0.9)
        return Position3D(x=self.width * 0.1, y=0, z=self.depth * 0.1)

    def get_door_swing_areas(self) -> list[BoundingBox]:
        """Get all door swing areas."""
        return [door.get_swing_area(self.width, self.depth) for door in self.doors]

    def get_natural_light_zones(self) -> list[BoundingBox]:
        """Get all natural light zones from windows."""
        return [
            window.get_natural_light_zone(self.width, self.depth)
            for window in self.windows
        ]

    def is_position_valid(self, position: Position3D) -> bool:
        """Check if a position is within room bounds."""
        return self.bounding_box.contains_point(position)

    def get_wall_length(self, wall: WallSide) -> float:
        """Get the length of a specific wall."""
        if wall.is_horizontal:
            return self.width
        return self.depth
