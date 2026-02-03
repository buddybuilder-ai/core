"""Spatial calculator tool for feng shui layout agent."""

from dataclasses import dataclass
from enum import Enum
from typing import Any

from src.modules.layout.domain.entities import DoorPosition, Room, WallSide, WindowPosition
from src.modules.layout.domain.value_objects import Position3D
from src.modules.layout.infrastructure.tools.base import BaseTool, ToolResult


class ZoneType(str, Enum):
    """Types of zones in a room."""

    COMMAND = "command"  # Best position for important furniture
    TRAFFIC = "traffic"  # Walking paths
    DOOR_SWING = "door_swing"  # Area where doors open
    WINDOW = "window"  # Area near windows
    CORNER = "corner"  # Corner areas
    CENTER = "center"  # Center of room
    WALL = "wall"  # Along walls


@dataclass(frozen=True)
class Zone:
    """A zone within the room.

    Attributes:
        zone_type: Type of the zone.
        x_min: Minimum x coordinate.
        x_max: Maximum x coordinate.
        z_min: Minimum z coordinate.
        z_max: Maximum z coordinate.
        priority: Priority score (higher = better for placement).
        notes: Additional notes about the zone.
    """

    zone_type: ZoneType
    x_min: float
    x_max: float
    z_min: float
    z_max: float
    priority: int = 0
    notes: str = ""

    @property
    def width(self) -> float:
        """Return width of the zone."""
        return self.x_max - self.x_min

    @property
    def depth(self) -> float:
        """Return depth of the zone."""
        return self.z_max - self.z_min

    @property
    def area(self) -> float:
        """Return area of the zone."""
        return self.width * self.depth

    @property
    def center(self) -> Position3D:
        """Return center position of the zone."""
        return Position3D(
            x=(self.x_min + self.x_max) / 2,
            y=0.0,
            z=(self.z_min + self.z_max) / 2,
        )

    def contains_point(self, x: float, z: float) -> bool:
        """Check if a point is within this zone."""
        return self.x_min <= x <= self.x_max and self.z_min <= z <= self.z_max

    def overlaps(self, other: "Zone") -> bool:
        """Check if this zone overlaps with another zone."""
        return not (
            self.x_max <= other.x_min
            or other.x_max <= self.x_min
            or self.z_max <= other.z_min
            or other.z_max <= self.z_min
        )


@dataclass(frozen=True)
class SpatialAnalysisInput:
    """Input for spatial analysis.

    Attributes:
        room: The room to analyze.
        clearance: Minimum clearance in meters (default 0.6m).
        door_swing_depth: Depth of door swing area in meters.
    """

    room: Room
    clearance: float = 0.6
    door_swing_depth: float = 1.0


@dataclass(frozen=True)
class SpatialAnalysisOutput:
    """Output of spatial analysis.

    Attributes:
        total_area: Total room area in square meters.
        usable_area: Usable area after removing traffic paths.
        zones: List of identified zones.
        command_positions: Best positions for important furniture.
        traffic_paths: Traffic path zones.
        blocked_areas: Areas that should not have furniture.
    """

    total_area: float
    usable_area: float
    zones: list[Zone]
    command_positions: list[Position3D]
    traffic_paths: list[Zone]
    blocked_areas: list[Zone]

    @property
    def usable_percentage(self) -> float:
        """Return percentage of usable area."""
        if self.total_area == 0:
            return 0.0
        return (self.usable_area / self.total_area) * 100

    def get_zones_by_type(self, zone_type: ZoneType) -> list[Zone]:
        """Get all zones of a specific type."""
        return [z for z in self.zones if z.zone_type == zone_type]


class SpatialCalculatorTool(BaseTool[SpatialAnalysisInput, SpatialAnalysisOutput]):
    """Tool for calculating spatial properties of a room.

    This tool analyzes a room and identifies:
    - Command positions (best placement spots)
    - Traffic paths
    - Door swing areas
    - Window areas
    - Available zones for furniture
    """

    @property
    def name(self) -> str:
        return "SPATIAL_CALCULATOR"

    @property
    def description(self) -> str:
        return (
            "Calculates spatial properties of a room including zones, "
            "traffic paths, command positions, and usable areas for furniture placement."
        )

    def validate_input(self, input_data: SpatialAnalysisInput) -> list[str]:
        """Validate the spatial analysis input."""
        errors = []
        if input_data.room.width <= 0:
            errors.append("Room width must be positive")
        if input_data.room.depth <= 0:
            errors.append("Room depth must be positive")
        if input_data.clearance < 0:
            errors.append("Clearance must be non-negative")
        if input_data.door_swing_depth < 0:
            errors.append("Door swing depth must be non-negative")
        return errors

    async def execute(self, input_data: SpatialAnalysisInput) -> ToolResult[SpatialAnalysisOutput]:
        """Execute spatial analysis on the room."""
        import time

        start_time = time.perf_counter()

        room = input_data.room
        clearance = input_data.clearance
        door_swing_depth = input_data.door_swing_depth

        zones: list[Zone] = []
        blocked_areas: list[Zone] = []
        traffic_paths: list[Zone] = []

        # Calculate door swing zones
        for door in room.doors:
            door_zone = self._calculate_door_swing_zone(room, door, door_swing_depth)
            zones.append(door_zone)
            blocked_areas.append(door_zone)

        # Calculate traffic paths from doors
        for door in room.doors:
            traffic_zone = self._calculate_traffic_path(room, door, clearance)
            zones.append(traffic_zone)
            traffic_paths.append(traffic_zone)

        # Calculate window zones
        for window in room.windows:
            window_zone = self._calculate_window_zone(room, window)
            zones.append(window_zone)

        # Calculate corner zones
        corner_zones = self._calculate_corner_zones(room, clearance)
        zones.extend(corner_zones)

        # Calculate center zone
        center_zone = self._calculate_center_zone(room)
        zones.append(center_zone)

        # Calculate command positions (feng shui)
        command_positions = self._calculate_command_positions(room, blocked_areas)

        # Calculate areas
        total_area = room.floor_area
        blocked_area = sum(z.area for z in blocked_areas)
        usable_area = max(0, total_area - blocked_area)

        elapsed_ms = (time.perf_counter() - start_time) * 1000

        output = SpatialAnalysisOutput(
            total_area=total_area,
            usable_area=usable_area,
            zones=zones,
            command_positions=command_positions,
            traffic_paths=traffic_paths,
            blocked_areas=blocked_areas,
        )

        return ToolResult.ok(
            data=output,
            execution_time_ms=elapsed_ms,
            metadata={
                "room_width": room.width,
                "room_depth": room.depth,
                "num_doors": len(room.doors),
                "num_windows": len(room.windows),
                "num_zones": len(zones),
            },
        )

    def _calculate_door_swing_zone(
        self, room: Room, door: DoorPosition, swing_depth: float
    ) -> Zone:
        """Calculate the zone where a door swings."""
        door_pos = self._get_door_position(room, door)
        door_width = door.width

        if door.wall == WallSide.NORTH:
            return Zone(
                zone_type=ZoneType.DOOR_SWING,
                x_min=max(0, door_pos.x - door_width / 2),
                x_max=min(room.width, door_pos.x + door_width / 2),
                z_min=0,
                z_max=swing_depth,
                priority=-10,
                notes="Door swing area - keep clear",
            )
        elif door.wall == WallSide.SOUTH:
            return Zone(
                zone_type=ZoneType.DOOR_SWING,
                x_min=max(0, door_pos.x - door_width / 2),
                x_max=min(room.width, door_pos.x + door_width / 2),
                z_min=room.depth - swing_depth,
                z_max=room.depth,
                priority=-10,
                notes="Door swing area - keep clear",
            )
        elif door.wall == WallSide.EAST:
            return Zone(
                zone_type=ZoneType.DOOR_SWING,
                x_min=room.width - swing_depth,
                x_max=room.width,
                z_min=max(0, door_pos.z - door_width / 2),
                z_max=min(room.depth, door_pos.z + door_width / 2),
                priority=-10,
                notes="Door swing area - keep clear",
            )
        else:  # WEST
            return Zone(
                zone_type=ZoneType.DOOR_SWING,
                x_min=0,
                x_max=swing_depth,
                z_min=max(0, door_pos.z - door_width / 2),
                z_max=min(room.depth, door_pos.z + door_width / 2),
                priority=-10,
                notes="Door swing area - keep clear",
            )

    def _calculate_traffic_path(
        self, room: Room, door: DoorPosition, clearance: float
    ) -> Zone:
        """Calculate traffic path from a door into the room."""
        door_pos = self._get_door_position(room, door)
        path_width = max(door.width, clearance * 2)

        if door.wall in (WallSide.NORTH, WallSide.SOUTH):
            return Zone(
                zone_type=ZoneType.TRAFFIC,
                x_min=max(0, door_pos.x - path_width / 2),
                x_max=min(room.width, door_pos.x + path_width / 2),
                z_min=0,
                z_max=room.depth,
                priority=-5,
                notes="Main traffic path - minimize obstructions",
            )
        else:  # EAST or WEST
            return Zone(
                zone_type=ZoneType.TRAFFIC,
                x_min=0,
                x_max=room.width,
                z_min=max(0, door_pos.z - path_width / 2),
                z_max=min(room.depth, door_pos.z + path_width / 2),
                priority=-5,
                notes="Main traffic path - minimize obstructions",
            )

    def _calculate_window_zone(self, room: Room, window: WindowPosition) -> Zone:
        """Calculate the zone near a window."""
        window_depth = 0.5  # 50cm from window

        if window.wall == WallSide.NORTH:
            return Zone(
                zone_type=ZoneType.WINDOW,
                x_min=max(0, window.offset - window.width / 2),
                x_max=min(room.width, window.offset + window.width / 2),
                z_min=0,
                z_max=window_depth,
                priority=5,
                notes="Window area - good for natural light",
            )
        elif window.wall == WallSide.SOUTH:
            return Zone(
                zone_type=ZoneType.WINDOW,
                x_min=max(0, window.offset - window.width / 2),
                x_max=min(room.width, window.offset + window.width / 2),
                z_min=room.depth - window_depth,
                z_max=room.depth,
                priority=5,
                notes="Window area - good for natural light",
            )
        elif window.wall == WallSide.EAST:
            return Zone(
                zone_type=ZoneType.WINDOW,
                x_min=room.width - window_depth,
                x_max=room.width,
                z_min=max(0, window.offset - window.width / 2),
                z_max=min(room.depth, window.offset + window.width / 2),
                priority=5,
                notes="Window area - good for natural light",
            )
        else:  # WEST
            return Zone(
                zone_type=ZoneType.WINDOW,
                x_min=0,
                x_max=window_depth,
                z_min=max(0, window.offset - window.width / 2),
                z_max=min(room.depth, window.offset + window.width / 2),
                priority=5,
                notes="Window area - good for natural light",
            )

    def _calculate_corner_zones(self, room: Room, clearance: float) -> list[Zone]:
        """Calculate corner zones of the room."""
        corner_size = clearance * 2
        corners = [
            Zone(
                zone_type=ZoneType.CORNER,
                x_min=0,
                x_max=corner_size,
                z_min=0,
                z_max=corner_size,
                priority=3,
                notes="Northwest corner",
            ),
            Zone(
                zone_type=ZoneType.CORNER,
                x_min=room.width - corner_size,
                x_max=room.width,
                z_min=0,
                z_max=corner_size,
                priority=3,
                notes="Northeast corner",
            ),
            Zone(
                zone_type=ZoneType.CORNER,
                x_min=0,
                x_max=corner_size,
                z_min=room.depth - corner_size,
                z_max=room.depth,
                priority=3,
                notes="Southwest corner",
            ),
            Zone(
                zone_type=ZoneType.CORNER,
                x_min=room.width - corner_size,
                x_max=room.width,
                z_min=room.depth - corner_size,
                z_max=room.depth,
                priority=3,
                notes="Southeast corner",
            ),
        ]
        return corners

    def _calculate_center_zone(self, room: Room) -> Zone:
        """Calculate the center zone of the room."""
        margin = min(room.width, room.depth) * 0.2
        return Zone(
            zone_type=ZoneType.CENTER,
            x_min=margin,
            x_max=room.width - margin,
            z_min=margin,
            z_max=room.depth - margin,
            priority=0,
            notes="Center area - good for main furniture",
        )

    def _calculate_command_positions(
        self, room: Room, blocked_areas: list[Zone]
    ) -> list[Position3D]:
        """Calculate command positions (feng shui optimal spots).

        Command position principles:
        1. Can see the door without being directly in line with it
        2. Has solid wall support behind
        3. Not in traffic path
        """
        command_positions: list[Position3D] = []

        # For each door, calculate diagonal command positions
        for door in room.doors:
            door_pos = self._get_door_position(room, door)

            # Calculate positions diagonal from door
            candidates = self._get_diagonal_positions(room, door_pos)

            # Filter out positions in blocked areas
            for pos in candidates:
                is_blocked = any(
                    zone.contains_point(pos.x, pos.z) for zone in blocked_areas
                )
                if not is_blocked:
                    command_positions.append(pos)

        # If no command positions found, use corners away from doors
        if not command_positions:
            command_positions = self._get_fallback_command_positions(room, blocked_areas)

        return command_positions

    def _get_door_position(self, room: Room, door: DoorPosition) -> Position3D:
        """Get the position of a door in room coordinates."""
        if door.wall == WallSide.NORTH:
            return Position3D(x=door.offset, y=0, z=0)
        elif door.wall == WallSide.SOUTH:
            return Position3D(x=door.offset, y=0, z=room.depth)
        elif door.wall == WallSide.EAST:
            return Position3D(x=room.width, y=0, z=door.offset)
        else:  # WEST
            return Position3D(x=0, y=0, z=door.offset)

    def _get_diagonal_positions(
        self, room: Room, door_pos: Position3D
    ) -> list[Position3D]:
        """Get diagonal positions from a door (command positions)."""
        positions = []
        margin = 0.8  # Distance from walls

        # Calculate corners that are diagonal from the door
        corners = [
            Position3D(x=margin, y=0, z=margin),  # NW
            Position3D(x=room.width - margin, y=0, z=margin),  # NE
            Position3D(x=margin, y=0, z=room.depth - margin),  # SW
            Position3D(x=room.width - margin, y=0, z=room.depth - margin),  # SE
        ]

        # Filter corners that are diagonal (not in line with door)
        for corner in corners:
            # Not directly in line with door (allowing some tolerance)
            in_x_line = abs(corner.x - door_pos.x) < 1.0
            in_z_line = abs(corner.z - door_pos.z) < 1.0

            # Prefer positions diagonal from door
            if not (in_x_line and in_z_line):
                positions.append(corner)

        return positions

    def _get_fallback_command_positions(
        self, room: Room, blocked_areas: list[Zone]
    ) -> list[Position3D]:
        """Get fallback command positions when diagonal positions are blocked."""
        margin = 0.8
        center_x = room.width / 2
        center_z = room.depth / 2

        candidates = [
            Position3D(x=center_x, y=0, z=margin),  # North center
            Position3D(x=center_x, y=0, z=room.depth - margin),  # South center
            Position3D(x=margin, y=0, z=center_z),  # West center
            Position3D(x=room.width - margin, y=0, z=center_z),  # East center
        ]

        positions = []
        for pos in candidates:
            is_blocked = any(
                zone.contains_point(pos.x, pos.z) for zone in blocked_areas
            )
            if not is_blocked:
                positions.append(pos)

        return positions if positions else [Position3D(x=center_x, y=0, z=center_z)]

    def to_langchain_tool_schema(self) -> dict[str, Any]:
        """Convert to LangChain tool schema."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "room_width": {
                        "type": "number",
                        "description": "Room width in meters",
                    },
                    "room_depth": {
                        "type": "number",
                        "description": "Room depth in meters",
                    },
                    "doors": {
                        "type": "array",
                        "description": "List of door positions",
                    },
                    "windows": {
                        "type": "array",
                        "description": "List of window positions",
                    },
                },
                "required": ["room_width", "room_depth"],
            },
        }
