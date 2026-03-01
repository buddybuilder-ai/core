"""Spatial resolver: converts semantic furniture placements to exact coordinates.

No LLM calls. All measurements in meters.
Coordinate system: origin at SW corner, x=east, z=north.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.modules.layout.domain.entities.room import DoorPosition, WindowPosition
from src.modules.layout.infrastructure.geometry.collision import AABB


@dataclass(frozen=True)
class FurnitureSize:
    """Physical dimensions of a furniture piece.

    Attributes:
        w: Width along x-axis in meters.
        l: Length along z-axis in meters.
        h: Height along y-axis in meters.
    """

    w: float
    l: float
    h: float


@dataclass(frozen=True)
class SemanticPlacement:
    """LLM-provided semantic placement intent for one furniture piece.

    Attributes:
        furniture_id: Unique identifier (e.g. "bed_01").
        furniture_type: Category name (e.g. "bed", "desk", "mirror").
        size: Physical dimensions.
        target_wall: Which wall to place against: north|south|east|west|center.
        alignment: Position along the wall: left|center|right.
        offset_from_wall: Gap between furniture and wall in meters.
        priority: Placement order (1 = first, lower wins ties).
        orientation: Informational hint (e.g. "headboard_against_wall").
    """

    furniture_id: str
    furniture_type: str
    size: FurnitureSize
    target_wall: str
    alignment: str
    offset_from_wall: float
    priority: int
    orientation: str = ""


@dataclass(frozen=True)
class PhysicalPlacement:
    """Resolved exact position for one furniture piece.

    Attributes:
        furniture_id: Matches the originating SemanticPlacement.
        x: Left edge of footprint in meters (x-axis).
        y: Always 0 (floor level).
        z: Bottom edge of footprint in meters (z-axis).
        rotation: Degrees clockwise from north-facing (0|90|180|270).
        bbox: 2-D axis-aligned bounding box of the footprint.
    """

    furniture_id: str
    x: float
    y: float
    z: float
    rotation: int
    bbox: AABB


@dataclass
class RoomSpec:
    """Minimal room specification needed by the spatial engine.

    Attributes:
        width: Room width along x-axis in meters.
        depth: Room depth along z-axis in meters.
        doors: List of door positions.
        windows: List of window positions.
    """

    width: float
    depth: float
    doors: list[DoorPosition] = field(default_factory=list)
    windows: list[WindowPosition] = field(default_factory=list)


# Rotation assigned to furniture placed against each wall so it faces inward.
_WALL_ROTATION: dict[str, int] = {
    "south": 180,  # south wall → faces north
    "north": 0,    # north wall → faces south
    "west": 90,    # west wall → faces east
    "east": 270,   # east wall → faces west
}


class SpatialResolver:
    """Converts a list of SemanticPlacements to exact PhysicalPlacements."""

    def resolve(
        self,
        placements: list[SemanticPlacement],
        room: RoomSpec,
    ) -> list[PhysicalPlacement]:
        """Resolve semantic placements to physical coordinates.

        Items are processed in ascending priority order (priority=1 first).

        Args:
            placements: Semantic descriptions from the LLM.
            room: Room dimensions and features.

        Returns:
            List of PhysicalPlacements sorted by priority.
        """
        sorted_items = sorted(placements, key=lambda p: p.priority)
        return [self._resolve_one(p, room) for p in sorted_items]

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _resolve_one(self, p: SemanticPlacement, room: RoomSpec) -> PhysicalPlacement:
        wall = p.target_wall.lower()
        if wall == "center":
            x, z, rotation = self._center_position(p, room)
        else:
            x, z, rotation = self._wall_position(p, room, wall)

        # Use actual footprint dimensions after rotation
        w, l = self._footprint(p.size, rotation)

        # Cap dimensions so item never exceeds room size
        w = min(w, room.width)
        l = min(l, room.depth)

        # Clamp origin so item stays fully inside room
        x = max(0.0, min(x, room.width - w))
        z = max(0.0, min(z, room.depth - l))

        bbox = AABB.from_position_and_size(x=x, z=z, width=w, depth=l)
        return PhysicalPlacement(
            furniture_id=p.furniture_id,
            x=x,
            y=0.0,
            z=z,
            rotation=rotation,
            bbox=bbox,
        )

    def _footprint(self, size: FurnitureSize, rotation: int) -> tuple[float, float]:
        """Return (width_x, depth_z) after applying rotation."""
        if rotation in (90, 270):
            return size.l, size.w
        return size.w, size.l

    def _center_position(
        self, p: SemanticPlacement, room: RoomSpec
    ) -> tuple[float, float, int]:
        w, l = self._footprint(p.size, 0)
        x = (room.width - w) / 2.0
        z = (room.depth - l) / 2.0
        return x, z, 0

    def _wall_position(
        self, p: SemanticPlacement, room: RoomSpec, wall: str
    ) -> tuple[float, float, int]:
        rotation = _WALL_ROTATION.get(wall, 0)
        w, l = self._footprint(p.size, rotation)
        gap = p.offset_from_wall

        if wall == "south":
            z = gap
            x = self._align_along_axis(p.alignment, w, room.width)
        elif wall == "north":
            z = room.depth - l - gap
            x = self._align_along_axis(p.alignment, w, room.width)
        elif wall == "west":
            x = gap
            z = self._align_along_axis(p.alignment, l, room.depth)
        elif wall == "east":
            x = room.width - w - gap
            z = self._align_along_axis(p.alignment, l, room.depth)
        else:
            x = gap
            z = gap

        return x, z, rotation

    @staticmethod
    def _align_along_axis(alignment: str, item_size: float, axis_length: float) -> float:
        """Return start-coordinate along an axis given alignment."""
        alignment = alignment.lower()
        if alignment == "center":
            return (axis_length - item_size) / 2.0
        if alignment == "right":
            return axis_length - item_size
        return 0.0  # "left" or fallback
