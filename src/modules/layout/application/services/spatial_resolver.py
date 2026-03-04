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
        length: Length along z-axis in meters.
        h: Height along y-axis in meters.
    """

    w: float
    length: float
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
        facing: Optional override for headboard/front direction independent of
                wall placement. E.g. target_wall="west" + facing="east" means
                place against west wall but rotate so headboard faces east.
                Values: north|south|east|west|"" (empty = use wall default).
    """

    furniture_id: str
    furniture_type: str
    size: FurnitureSize
    target_wall: str
    alignment: str
    offset_from_wall: float
    priority: int
    orientation: str = ""
    facing: str = ""


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
# Three.js Y=0° → faces -Z (north); Y=180° → faces +Z (south).
_WALL_ROTATION: dict[str, int] = {
    "south": 180,  # south wall → faces into room (Y=180° → +Z)
    "north": 0,  # north wall → faces into room (Y=0° → -Z)
    "west": 90,  # west wall → faces east  (Y=90° → +X)
    "east": 270,  # east wall → faces west  (Y=270° → -X)
}

# Opposite of each wall — used for auto-facing "must face inward"
_OPPOSITE_WALL: dict[str, str] = {
    "south": "north",
    "north": "south",
    "east": "west",
    "west": "east",
}

# Furniture types that MUST face inward (away from their wall) regardless of LLM output.
# These are items where "facing the wall" is physically nonsensical.
# Value = "inward" means: use opposite of target_wall as facing.
_FORCE_INWARD_TYPES: frozenset[str] = frozenset(
    {
        "chair",
        "office_chair",
        "armchair",
        "dining_chair",
        "desk",
        "folding_desk",
        "sofa",
        "sofa_bed",
        "tv_stand",  # screen must face into room
    }
)

# Rotation to apply when the LLM specifies which direction the front/seat faces.
# Three.js Y-rotation is CCW from above (right-hand rule).
# Frontend coordinate: south wall = +Z, north wall = -Z, east = +X, west = -X.
#   Y=0°   → model front faces -Z = north
#   Y=180° → model front faces +Z = south
#   Y=90°  → model front faces +X = east
#   Y=270° → model front faces -X = west
_FACING_ROTATION: dict[str, int] = {
    "south": 180,  # front faces +Z (toward south wall)  Y=180° → +Z
    "north": 0,  # front faces -Z (toward north wall)  Y=0°   → -Z
    "east": 90,  # front faces +X (toward east wall)   Y=90°  → +X
    "west": 270,  # front faces -X (toward west wall)   Y=270° → -X
}


class SpatialResolver:
    """Converts a list of SemanticPlacements to exact PhysicalPlacements."""

    # Step distances tried by the bump-out pass
    _BUMP_STEPS = [0.1, 0.2, 0.3, 0.5, 0.8, 1.0, 1.5]

    # Minimum clearance in front of a door (meters) — kept free for walking
    _DOOR_CLEARANCE = 0.9

    def _door_zones(self, room: RoomSpec) -> list[AABB]:
        """Return clearance AABBs in front of each door that must stay empty."""
        zones: list[AABB] = []
        c = self._DOOR_CLEARANCE
        # Door width assumed ~0.9 m; clearance rectangle extends inward from the door wall
        # Clearance starts slightly inward from the wall so that furniture
        # hugging the same wall is not considered to block the door.
        _MIN_GAP = 0.15
        for door in room.doors:
            wall = str(getattr(door, "wall", "")).lower()
            # Estimate door x/z position from offset (DoorPosition uses .offset field)
            offset = float(getattr(door, "offset", getattr(door, "offset_from_corner", 0.0)))
            door_w = float(getattr(door, "width", 0.9))
            if wall == "south":
                x0 = max(0.0, offset - 0.1)
                x1 = min(room.width, offset + door_w + 0.1)
                zones.append(AABB(min_x=x0, max_x=x1, min_z=_MIN_GAP, max_z=c))
            elif wall == "north":
                x0 = max(0.0, offset - 0.1)
                x1 = min(room.width, offset + door_w + 0.1)
                zones.append(
                    AABB(min_x=x0, max_x=x1, min_z=room.depth - c, max_z=room.depth - _MIN_GAP)
                )
            elif wall == "west":
                z0 = max(0.0, offset - 0.1)
                z1 = min(room.depth, offset + door_w + 0.1)
                zones.append(AABB(min_x=_MIN_GAP, max_x=c, min_z=z0, max_z=z1))
            elif wall == "east":
                z0 = max(0.0, offset - 0.1)
                z1 = min(room.depth, offset + door_w + 0.1)
                zones.append(
                    AABB(min_x=room.width - c, max_x=room.width - _MIN_GAP, min_z=z0, max_z=z1)
                )
        return zones

    def resolve(
        self,
        placements: list[SemanticPlacement],
        room: RoomSpec,
    ) -> list[PhysicalPlacement]:
        """Resolve semantic placements to physical coordinates.

        Items are processed in ascending priority order (priority=1 first).
        After placing each item a bump-out pass moves it away from already-placed
        items so the output is collision-free (best-effort).

        Args:
            placements: Semantic descriptions from the LLM.
            room: Room dimensions and features.

        Returns:
            List of PhysicalPlacements sorted by priority.
        """
        sorted_items = sorted(placements, key=lambda p: p.priority)
        placed: list[PhysicalPlacement] = []
        door_zones = self._door_zones(room)
        for p in sorted_items:
            result = self._resolve_one(p, room)
            result = self._bump_out(result, placed, room, door_zones)
            placed.append(result)
        return placed

    def _bump_out(
        self,
        item: PhysicalPlacement,
        placed: list[PhysicalPlacement],
        room: RoomSpec,
        door_zones: list[AABB] | None = None,
    ) -> PhysicalPlacement:
        """Shift *item* away from already-placed items until no overlap.

        Direction priority keeps wall-hugging items on their wall:
        1. Lateral (along the wall) — both directions
        2. Away from wall (into room centre) — last resort
        This prevents furniture being torn off its wall just because another
        piece is already there.

        Also avoids blocking door clearance zones (90 cm in front of each door).
        """
        w = item.bbox.max_x - item.bbox.min_x
        d = item.bbox.max_z - item.bbox.min_z
        _door_zones = door_zones or []

        def overlaps_any(x: float, z: float) -> bool:
            box = AABB.from_position_and_size(x, z, w, d)
            if any(box.intersects(p.bbox) for p in placed):
                return True
            # Don't block door clearance zones
            return any(box.intersects(dz) for dz in _door_zones)

        if not overlaps_any(item.x, item.z):
            return item  # already clear

        # Detect which wall(s) the item is hugging (within 0.1 m tolerance)
        _WALL_TOL = 0.1
        on_south = item.z <= _WALL_TOL
        on_north = item.z >= room.depth - d - _WALL_TOL
        on_west = item.x <= _WALL_TOL
        on_east = item.x >= room.width - w - _WALL_TOL

        # For wall-hugging items: slide ALONG the wall first, then push inward.
        # For floating/center items: try all directions toward room centre.
        cx = (room.width - w) / 2.0
        cz = (room.depth - d) / 2.0
        dx_center = 1 if item.x < cx else -1
        dz_center = 1 if item.z < cz else -1

        if on_south or on_north:
            # On a z-wall → slide along x first, then push in z
            dirs = [
                (1, 0),
                (-1, 0),  # slide right / left along wall
                (dx_center, 0),  # slide toward x-centre
                (0, dz_center),  # push away from wall (last resort)
                (dx_center, dz_center),
                (-dx_center, dz_center),
            ]
        elif on_west or on_east:
            # On an x-wall → slide along z first, then push in x
            dirs = [
                (0, 1),
                (0, -1),  # slide up / down along wall
                (0, dz_center),  # slide toward z-centre
                (dx_center, 0),  # push away from wall (last resort)
                (dx_center, dz_center),
                (dx_center, -dz_center),
            ]
        else:
            # Floating / center placement — original centre-first logic
            dirs = [
                (dx_center, 0),
                (0, dz_center),
                (dx_center, dz_center),
                (-dx_center, 0),
                (0, -dz_center),
                (dx_center, -dz_center),
                (-dx_center, dz_center),
                (-dx_center, -dz_center),
            ]

        for step in self._BUMP_STEPS:
            for dx, dz in dirs:
                nx = max(0.0, min(item.x + dx * step, room.width - w))
                nz = max(0.0, min(item.z + dz * step, room.depth - d))
                if not overlaps_any(nx, nz):
                    new_bbox = AABB.from_position_and_size(nx, nz, w, d)
                    return PhysicalPlacement(
                        furniture_id=item.furniture_id,
                        x=round(nx, 3),
                        y=item.y,
                        z=round(nz, 3),
                        rotation=item.rotation,
                        bbox=new_bbox,
                    )

        return item  # could not resolve — return as-is

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _resolve_one(self, p: SemanticPlacement, room: RoomSpec) -> PhysicalPlacement:
        wall = p.target_wall.lower()
        if wall == "center":
            x, z, rotation = self._center_position(p, room)
        else:
            x, z, rotation = self._wall_position(p, room, wall)

        # --- Facing resolution (3-tier priority) ---
        # 1. LLM explicitly set facing → always honour it
        # 2. furniture_type is in _FORCE_INWARD_TYPES and facing is empty
        #    → force facing = opposite of target_wall (away from wall = usable)
        # 3. Otherwise keep wall-default rotation from _WALL_ROTATION
        ftype = p.furniture_type.lower().replace("-", "_").replace(" ", "_")
        effective_facing = p.facing

        if not effective_facing and wall != "center":
            if ftype in _FORCE_INWARD_TYPES:
                effective_facing = _OPPOSITE_WALL.get(wall, "")

        if effective_facing and effective_facing in _FACING_ROTATION:
            rotation = _FACING_ROTATION[effective_facing]

        # Use actual footprint dimensions after rotation
        w, length = self._footprint(p.size, rotation)

        # Cap dimensions so item never exceeds room size
        w = min(w, room.width)
        length = min(length, room.depth)

        # Clamp origin so item stays fully inside room
        x = max(0.0, min(x, room.width - w))
        z = max(0.0, min(z, room.depth - length))

        bbox = AABB.from_position_and_size(x=x, z=z, width=w, depth=length)
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
            return size.length, size.w
        return size.w, size.length

    def _center_position(self, p: SemanticPlacement, room: RoomSpec) -> tuple[float, float, int]:
        w, length = self._footprint(p.size, 0)
        x = (room.width - w) / 2.0
        z = (room.depth - length) / 2.0
        return x, z, 0

    def _wall_position(
        self, p: SemanticPlacement, room: RoomSpec, wall: str
    ) -> tuple[float, float, int]:
        rotation = _WALL_ROTATION.get(wall, 0)
        w, length = self._footprint(p.size, rotation)
        gap = p.offset_from_wall

        if wall == "south":
            z = gap
            x = self._align_along_axis(p.alignment, w, room.width)
        elif wall == "north":
            z = room.depth - length - gap
            x = self._align_along_axis(p.alignment, w, room.width)
        elif wall == "west":
            x = gap
            z = self._align_along_axis(p.alignment, length, room.depth)
        elif wall == "east":
            x = room.width - w - gap
            z = self._align_along_axis(p.alignment, length, room.depth)
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
