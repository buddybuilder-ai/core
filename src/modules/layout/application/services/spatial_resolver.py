"""Spatial resolver: converts semantic furniture placements to exact coordinates.

No LLM calls. All measurements in meters.
Coordinate system: origin at SW corner, x=east, z=north.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

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


# Rotation assigned to furniture placed against each wall so its back is
# against the wall and its front (+Z at rest) faces into the room.
# Three.js Y-rotation CCW from above; front = +Z.
#   south wall → front must face north(-Z) → Y=180°
#   north wall → front must face south(+Z) → Y=0°
#   west wall  → front must face east(+X)  → Y=90°
#   east wall  → front must face west(-X)  → Y=270°
_WALL_ROTATION: dict[str, int] = {
    "south": 180,
    "north": 0,
    "west": 90,
    "east": 270,
}

# Opposite of each wall — used for auto-facing "must face inward"
_OPPOSITE_WALL: dict[str, str] = {
    "south": "north",
    "north": "south",
    "east": "west",
    "west": "east",
}

# Furniture types placed beside the door (not in front of it).
# SpatialResolver will compute their x/z from actual door position instead of
# using generic left/right alignment which may land them in front of the door.
_DOOR_ADJACENT_TYPES: frozenset[str] = frozenset({"shoe_cabinet", "coat_rack"})

# Gap between door-adjacent furniture and the door edge (meters)
_DOOR_ADJACENT_GAP = 0.1

# Furniture types that MUST face inward (away from their wall) regardless of LLM output.
# These are items where "facing the wall" is physically nonsensical.
# Value = "inward" means: use opposite of target_wall as facing.
_FORCE_INWARD_TYPES: frozenset[str] = frozenset(
    {
        "bed",              # headboard against wall, occupant faces into room
        "chair",
        "office_chair",
        "armchair",
        "dining_chair",
        "desk",
        "folding_desk",
        "sofa",
        "sofa_bed",
        "tv_stand",         # screen must face into room
        "wardrobe",         # door must open into room
        "compact_wardrobe",
        "bookshelf",        # books must be accessible
        "nightstand",       # drawers face outward
        "dresser",
        "shoe_cabinet",
        "kitchen_counter",  # work surface faces into room
        "mini_fridge",      # door must open into room
    }
)

# Rotation to apply when the LLM specifies which direction the front/seat faces.
# facing="south" means front points toward south (+Z in Three.js) → Y=0°
# facing="north" means front points toward north (-Z in Three.js) → Y=180°
# facing="east"  means front points toward east  (+X)             → Y=270°
# facing="west"  means front points toward west  (-X)             → Y=90°
_FACING_ROTATION: dict[str, int] = {
    "south": 0,
    "north": 180,
    "east": 270,
    "west": 90,
}


class SpatialResolver:
    """Converts a list of SemanticPlacements to exact PhysicalPlacements."""

    # Step distances tried by the bump-out pass
    _BUMP_STEPS = [0.1, 0.2, 0.3, 0.5, 0.8, 1.0, 1.5]

    # Minimum clearance in front of a door (meters) — kept free for walking
    _DOOR_CLEARANCE = 1.5

    def _door_zones(self, room: RoomSpec) -> list[AABB]:
        """Return clearance AABBs that must stay empty around each door.

        Two zones per door:
        1. Door opening (the doorway itself — items must not block the opening)
        2. Walking clearance (1.5 m into room from door wall)
        """
        zones: list[AABB] = []
        c = self._DOOR_CLEARANCE
        _MIN_GAP = 0.0   # door opening starts at the wall itself
        _CLEAR_GAP = 0.15  # walking clearance starts 15cm inside
        _SIDE_PAD = 0.5
        for door in room.doors:
            wall = str(getattr(door, "wall", "")).lower()
            offset = float(getattr(door, "offset", getattr(door, "offset_from_corner", 0.0)))
            door_w = float(getattr(door, "width", 0.9))
            logger.info(f"_door_zones: door wall={wall} offset={offset:.3f}m width={door_w:.3f}m clearance={c}m")
            if wall == "south":
                # Zone 1: door opening along south wall (x: door span, z: 0 → wall thickness ~0.15m)
                zones.append(AABB(min_x=offset, max_x=offset + door_w, min_z=_MIN_GAP, max_z=_CLEAR_GAP))
                # Zone 2: walking clearance in front of door
                x0 = max(0.0, offset - _SIDE_PAD)
                x1 = min(room.width, offset + door_w + _SIDE_PAD)
                zones.append(AABB(min_x=x0, max_x=x1, min_z=_CLEAR_GAP, max_z=c))
            elif wall == "north":
                zones.append(AABB(min_x=offset, max_x=offset + door_w,
                                  min_z=room.depth - _CLEAR_GAP, max_z=room.depth))
                x0 = max(0.0, offset - _SIDE_PAD)
                x1 = min(room.width, offset + door_w + _SIDE_PAD)
                zones.append(AABB(min_x=x0, max_x=x1, min_z=room.depth - c, max_z=room.depth - _CLEAR_GAP))
            elif wall == "west":
                zones.append(AABB(min_x=_MIN_GAP, max_x=_CLEAR_GAP,
                                  min_z=offset, max_z=offset + door_w))
                z0 = max(0.0, offset - _SIDE_PAD)
                z1 = min(room.depth, offset + door_w + _SIDE_PAD)
                zones.append(AABB(min_x=_CLEAR_GAP, max_x=c, min_z=z0, max_z=z1))
            elif wall == "east":
                zones.append(AABB(min_x=room.width - _CLEAR_GAP, max_x=room.width,
                                  min_z=offset, max_z=offset + door_w))
                z0 = max(0.0, offset - _SIDE_PAD)
                z1 = min(room.depth, offset + door_w + _SIDE_PAD)
                zones.append(AABB(min_x=room.width - c, max_x=room.width - _CLEAR_GAP, min_z=z0, max_z=z1))
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
        _GAP = 0.05  # minimum gap between furniture pieces

        # Detect which wall(s) the item is hugging (within 0.1 m tolerance)
        _WALL_TOL = 0.1
        on_south = item.z <= _WALL_TOL
        on_north = item.z >= room.depth - d - _WALL_TOL
        on_west = item.x <= _WALL_TOL
        on_east = item.x >= room.width - w - _WALL_TOL

        # Which walls have a door? Used to decide if a wall-hugging item
        # should still respect door clearance zones.
        door_walls: set[str] = {
            str(getattr(door, "wall", "")).lower() for door in room.doors
        }

        # Door-adjacent items (shoe_cabinet, coat_rack) are intentionally placed
        # beside the door by _door_adjacent_x — exempt them from walking clearance
        # zones but NOT from the door opening itself (must not block the door).
        # PhysicalPlacement has no furniture_type; detect from furniture_id instead.
        fid_lower = item.furniture_id.lower().replace("-", "_")
        is_door_adjacent = any(t in fid_lower for t in _DOOR_ADJACENT_TYPES)

        # Pre-compute door opening AABBs (zone index 0 of each door pair = opening zone)
        # _door_zones returns [opening, clearance, opening, clearance, ...]
        _door_opening_zones = _door_zones[0::2]  # every other starting at 0 = door opening AABBs

        def overlaps_any(x: float, z: float) -> bool:
            box = AABB.from_position_and_size(x, z, w, d)
            # Expand check box by _GAP to enforce minimum spacing between items
            box_padded = AABB(
                min_x=box.min_x - _GAP, max_x=box.max_x + _GAP,
                min_z=box.min_z - _GAP, max_z=box.max_z + _GAP,
            )
            if any(box_padded.intersects(p.bbox) for p in placed):
                return True
            # Door openings are never OK to block — check for all items
            if any(box.intersects(dz) for dz in _door_opening_zones):
                return True
            if is_door_adjacent:
                # Door-adjacent items CAN sit in clearance zone only when truly
                # flush against the door wall (depth ≤ 15 cm from wall).
                # If they've drifted into the walking path, treat as blocked.
                _CLEAR_GAP = 0.15
                flush_south = on_south and (z + d) <= _CLEAR_GAP
                flush_north = on_north and z >= room.depth - _CLEAR_GAP
                flush_west = on_west and (x + w) <= _CLEAR_GAP
                flush_east = on_east and x >= room.width - _CLEAR_GAP
                if flush_south or flush_north or flush_west or flush_east:
                    return False  # truly flush — OK
                # Not flush: apply full door zone check
                return any(box.intersects(dz) for dz in _door_zones)
            # Wall-hugging items on a wall that has NO door may skip door-zone
            # checks (they can't block a door that isn't on their wall).
            # Items on the SAME wall as a door must still respect clearance.
            if on_south and "south" not in door_walls:
                return False
            if on_north and "north" not in door_walls:
                return False
            if on_west and "west" not in door_walls:
                return False
            if on_east and "east" not in door_walls:
                return False
            return any(box.intersects(dz) for dz in _door_zones)

        if not overlaps_any(item.x, item.z):
            return item  # already clear

        # Door-adjacent items have a fixed position beside the door.
        # If they still overlap, first try the other side of the door, then
        # slide along the wall. Never push to another wall.
        if is_door_adjacent:
            # Try opposite side of door first (if item was placed left, try right and vice versa)
            for door in room.doors:
                door_wall = str(getattr(door, "wall", "")).lower()
                door_offset = float(getattr(door, "offset", 0.0))
                door_dw = float(getattr(door, "width", 0.9))
                _ADJ_GAP = 0.1
                axis_len = room.width if door_wall in ("south", "north") else room.depth
                right_x = door_offset + door_dw + _ADJ_GAP
                left_x = door_offset - w - _ADJ_GAP
                for candidate_x in [right_x, left_x]:
                    candidate_x = max(0.0, min(candidate_x, axis_len - w))
                    if door_wall in ("south", "north"):
                        nx, nz = candidate_x, item.z
                    else:
                        nx, nz = item.x, candidate_x
                    if not overlaps_any(nx, nz):
                        new_bbox = AABB.from_position_and_size(nx, nz, w, d)
                        logger.info(
                            f"_bump_out door_adjacent: {item.furniture_id} "
                            f"switched side → ({nx:.3f},{nz:.3f})"
                        )
                        return PhysicalPlacement(
                            furniture_id=item.furniture_id,
                            x=round(nx, 3),
                            y=item.y,
                            z=round(nz, 3),
                            rotation=item.rotation,
                            bbox=new_bbox,
                        )

            # Slide along the wall axis only, using fine steps
            if on_south or on_north:
                slide_dirs = [(1, 0), (-1, 0)]
            elif on_west or on_east:
                slide_dirs = [(0, 1), (0, -1)]
            else:
                slide_dirs = [(1, 0), (-1, 0), (0, 1), (0, -1)]
            fine_steps = [0.05, 0.1, 0.15, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 1.0, 1.2, 1.5, 2.0]
            for step in fine_steps:
                for dx, dz in slide_dirs:
                    nx = max(0.0, min(item.x + dx * step, room.width - w))
                    nz = max(0.0, min(item.z + dz * step, room.depth - d))
                    if not overlaps_any(nx, nz):
                        new_bbox = AABB.from_position_and_size(nx, nz, w, d)
                        logger.info(
                            f"_bump_out door_adjacent: {item.furniture_id} "
                            f"slid from ({item.x:.3f},{item.z:.3f}) → ({nx:.3f},{nz:.3f}) step={step}"
                        )
                        return PhysicalPlacement(
                            furniture_id=item.furniture_id,
                            x=round(nx, 3),
                            y=item.y,
                            z=round(nz, 3),
                            rotation=item.rotation,
                            bbox=new_bbox,
                        )
            logger.warning(f"_bump_out door_adjacent: {item.furniture_id} cannot slide — placed as-is")
            return item  # cannot move — place as-is beside door

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

        # --- Fallback: try placing against each alternative wall ---
        # Original wall is full; attempt the other 3 walls in order.
        alt_walls = ["south", "north", "west", "east"]
        if on_south:
            alt_walls = ["north", "west", "east"]
        elif on_north:
            alt_walls = ["south", "west", "east"]
        elif on_west:
            alt_walls = ["east", "south", "north"]
        elif on_east:
            alt_walls = ["west", "south", "north"]

        for alt_wall in alt_walls:
            alt_rot = _WALL_ROTATION.get(alt_wall, item.rotation)
            # Recompute footprint for the new rotation (w/d may swap at 90/270)
            if alt_rot in (90, 270):
                aw, ad = d, w  # swap
            else:
                aw, ad = w, d

            # Clamp to room
            aw = min(aw, room.width)
            ad = min(ad, room.depth)

            if alt_wall == "south":
                nx, nz = (room.width - aw) / 2.0, 0.0
            elif alt_wall == "north":
                nx, nz = (room.width - aw) / 2.0, room.depth - ad
            elif alt_wall == "west":
                nx, nz = 0.0, (room.depth - ad) / 2.0
            else:  # east
                nx, nz = room.width - aw, (room.depth - ad) / 2.0

            # Check with the new dimensions
            def overlaps_alt(x: float, z: float, fw: float, fd: float) -> bool:
                box = AABB.from_position_and_size(x, z, fw, fd)
                return any(box.intersects(p.bbox) for p in placed)

            if not overlaps_alt(nx, nz, aw, ad):
                new_bbox = AABB.from_position_and_size(nx, nz, aw, ad)
                return PhysicalPlacement(
                    furniture_id=item.furniture_id,
                    x=round(nx, 3),
                    y=item.y,
                    z=round(nz, 3),
                    rotation=alt_rot,
                    bbox=new_bbox,
                )

            # Also try sliding along the alt wall
            for step in self._BUMP_STEPS:
                for slide in [1, -1]:
                    if alt_wall in ("south", "north"):
                        sx, sz = nx + slide * step, nz
                        sx = max(0.0, min(sx, room.width - aw))
                    else:
                        sx, sz = nx, nz + slide * step
                        sz = max(0.0, min(sz, room.depth - ad))
                    if not overlaps_alt(sx, sz, aw, ad):
                        new_bbox = AABB.from_position_and_size(sx, sz, aw, ad)
                        return PhysicalPlacement(
                            furniture_id=item.furniture_id,
                            x=round(sx, 3),
                            y=item.y,
                            z=round(sz, 3),
                            rotation=alt_rot,
                            bbox=new_bbox,
                        )

        return item  # could not resolve — return as-is

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _resolve_one(self, p: SemanticPlacement, room: RoomSpec) -> PhysicalPlacement:
        wall = p.target_wall.lower()

        # --- Determine final rotation BEFORE computing position ---
        # so _wall_position uses the correct footprint.
        ftype = p.furniture_type.lower().replace("-", "_").replace(" ", "_")
        effective_facing = p.facing

        if wall != "center" and ftype in _FORCE_INWARD_TYPES:
            # Force inward: use _WALL_ROTATION directly (designed for "back against wall,
            # front into room") instead of going through _FACING_ROTATION which has
            # an inverted convention that causes the furniture to face the wall.
            rotation = _WALL_ROTATION.get(wall, 0)
            effective_facing = _OPPOSITE_WALL.get(wall, "")
        elif effective_facing and effective_facing in _FACING_ROTATION:
            rotation = _FACING_ROTATION[effective_facing]
        else:
            rotation = _WALL_ROTATION.get(wall, 0) if wall != "center" else 0

        # --- Compute position using the final rotation ---
        if wall == "center":
            x, z, _ = self._center_position(p, room)
        else:
            x, z = self._wall_position_xy(p, room, wall, rotation)

        logger.info(
            f"_resolve_one: fid={p.furniture_id} wall={wall} facing={p.facing!r} "
            f"effective_facing={effective_facing!r} ftype={ftype!r} "
            f"force_inward={ftype in _FORCE_INWARD_TYPES} rotation={rotation} "
            f"x={x:.3f} z={z:.3f}"
        )

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
        x, z = self._wall_position_xy(p, room, wall, rotation)
        return x, z, rotation

    def _wall_position_xy(
        self, p: SemanticPlacement, room: RoomSpec, wall: str, rotation: int
    ) -> tuple[float, float]:
        """Compute x, z for furniture against *wall* using the given rotation for footprint."""
        w, length = self._footprint(p.size, rotation)
        gap = p.offset_from_wall

        ftype = p.furniture_type.lower().replace("-", "_").replace(" ", "_")
        if ftype in _DOOR_ADJACENT_TYPES and room.doors:
            door_x = self._door_adjacent_x(p.alignment, w, wall, room)
            if door_x is not None:
                if wall == "south":
                    return door_x, gap
                elif wall == "north":
                    return door_x, room.depth - length - gap
                elif wall == "west":
                    return gap, door_x
                elif wall == "east":
                    return room.width - w - gap, door_x

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

        return x, z

    def _door_adjacent_x(
        self, alignment: str, item_size: float, wall: str, room: RoomSpec
    ) -> float | None:
        """Return start-coordinate placing item beside the door (not in front of it).

        Items are placed as close to the door as possible while keeping the
        doorway itself clear. WallAssigner already checked which side fits —
        spatial_resolver just computes the exact coordinate.

        alignment='left'  → place to the left  of the door
        alignment='right' → place to the right of the door
        Returns None if no door is on this wall.
        """
        door = next(
            (d for d in room.doors if str(getattr(d, "wall", "")).lower() == wall),
            None,
        )
        if door is None:
            return None

        door_offset = float(getattr(door, "offset", 0.0))
        door_width = float(getattr(door, "width", 0.9))
        axis_length = room.width if wall in ("south", "north") else room.depth

        left_x = door_offset - item_size - _DOOR_ADJACENT_GAP
        right_x = door_offset + door_width + _DOOR_ADJACENT_GAP
        left_fits = left_x >= 0.0
        right_fits = right_x + item_size <= axis_length

        if alignment.lower() == "left":
            x = left_x if left_fits else (right_x if right_fits else max(0.0, left_x))
        else:
            x = right_x if right_fits else (left_x if left_fits else min(axis_length - item_size, right_x))

        logger.info(
            f"_door_adjacent_x: {alignment} of door(offset={door_offset}, w={door_width}) "
            f"→ x={x:.3f} (item_size={item_size:.3f}, left_fits={left_fits}, right_fits={right_fits})"
        )
        return x

    @staticmethod
    def _align_along_axis(alignment: str, item_size: float, axis_length: float) -> float:
        """Return start-coordinate along an axis given alignment."""
        alignment = alignment.lower()
        if alignment == "center":
            return (axis_length - item_size) / 2.0
        if alignment == "right":
            return axis_length - item_size
        return 0.0  # "left" or fallback
