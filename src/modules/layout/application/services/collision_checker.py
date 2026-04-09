"""Collision checker for resolved furniture placements.

Checks:
  - out_of_bounds: furniture footprint extends outside room
  - overlap: two furniture footprints intersect
  - door_blocked: furniture inside 150 cm clearance zone in front of a door (±50 cm side padding)
  - insufficient_clearance: less than 60 cm between two items

No LLM calls. All measurements in meters.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.modules.layout.application.services.spatial_resolver import (
    PhysicalPlacement,
    RoomSpec,
)
from src.modules.layout.domain.entities.room import DoorPosition, WallSide
from src.modules.layout.infrastructure.geometry.collision import AABB

DOOR_CLEARANCE = 1.50  # metres — matches spatial_resolver._DOOR_CLEARANCE
DOOR_SIDE_PAD = 0.50  # metres — lateral padding either side of doorway
WALKWAY_CLEARANCE = 0.60  # metres


@dataclass(frozen=True)
class Collision:
    """A detected spatial problem between furniture or boundaries.

    Attributes:
        type: overlap|out_of_bounds|door_blocked|insufficient_clearance
        severity: critical|major|minor
        furniture_ids: IDs of furniture involved (1 or 2 items).
        description: Human-readable explanation with measurements.
    """

    type: str
    severity: str
    furniture_ids: list[str]
    description: str


def check_collisions(
    placements: list[PhysicalPlacement],
    room: RoomSpec,
) -> list[Collision]:
    """Run all collision checks on a list of resolved placements.

    Args:
        placements: Output of SpatialResolver.resolve().
        room: Room dimensions and features.

    Returns:
        List of Collision objects, empty if layout is clean.
    """
    results: list[Collision] = []
    results.extend(_check_out_of_bounds(placements, room))
    results.extend(_check_overlaps(placements))
    results.extend(_check_door_clearances(placements, room))
    results.extend(_check_walkway_clearances(placements, room))
    return results


# ---------------------------------------------------------------------------
# Individual check functions
# ---------------------------------------------------------------------------


def _check_out_of_bounds(placements: list[PhysicalPlacement], room: RoomSpec) -> list[Collision]:
    collisions: list[Collision] = []
    for p in placements:
        b = p.bbox
        if b.min_x < 0 or b.min_z < 0 or b.max_x > room.width or b.max_z > room.depth:
            overflow_x = max(0.0, -b.min_x, b.max_x - room.width)
            overflow_z = max(0.0, -b.min_z, b.max_z - room.depth)
            overflow = max(overflow_x, overflow_z)
            collisions.append(
                Collision(
                    type="out_of_bounds",
                    severity="critical",
                    furniture_ids=[p.furniture_id],
                    description=f"{p.furniture_id} extends {overflow:.2f}m outside room bounds",
                )
            )
    return collisions


def _check_overlaps(placements: list[PhysicalPlacement]) -> list[Collision]:
    collisions: list[Collision] = []
    for i, a in enumerate(placements):
        for b in placements[i + 1 :]:
            if not a.bbox.intersects(b.bbox):
                continue
            inter = a.bbox.intersection(b.bbox)
            if inter is None:
                continue
            if inter.width <= inter.depth:
                axis_desc = f"{inter.width:.2f}m on x-axis"
            else:
                axis_desc = f"{inter.depth:.2f}m on z-axis"
            collisions.append(
                Collision(
                    type="overlap",
                    severity="critical",
                    furniture_ids=[a.furniture_id, b.furniture_id],
                    description=(f"{a.furniture_id} overlaps with {b.furniture_id} by {axis_desc}"),
                )
            )
    return collisions


def _door_clearance_box(door: DoorPosition, room: RoomSpec) -> AABB:
    """Return the AABB that must remain clear in front of a door.

    Matches the zone produced by spatial_resolver._door_zones():
    - Depth: DOOR_CLEARANCE (1.5 m) into the room from the door wall
    - Width: door opening + DOOR_SIDE_PAD (0.5 m) on each side
    """
    off, w, c, pad = door.offset, door.width, DOOR_CLEARANCE, DOOR_SIDE_PAD
    if door.wall == WallSide.SOUTH:
        x0 = max(0.0, off - pad)
        x1 = min(room.width, off + w + pad)
        return AABB(min_x=x0, min_z=0.0, max_x=x1, max_z=c)
    if door.wall == WallSide.NORTH:
        x0 = max(0.0, off - pad)
        x1 = min(room.width, off + w + pad)
        return AABB(min_x=x0, min_z=room.depth - c, max_x=x1, max_z=room.depth)
    if door.wall == WallSide.WEST:
        z0 = max(0.0, off - pad)
        z1 = min(room.depth, off + w + pad)
        return AABB(min_x=0.0, min_z=z0, max_x=c, max_z=z1)
    # EAST
    z0 = max(0.0, off - pad)
    z1 = min(room.depth, off + w + pad)
    return AABB(min_x=room.width - c, min_z=z0, max_x=room.width, max_z=z1)


def _check_door_clearances(placements: list[PhysicalPlacement], room: RoomSpec) -> list[Collision]:
    collisions: list[Collision] = []
    for i, door in enumerate(room.doors):
        clear_box = _door_clearance_box(door, room)
        for p in placements:
            if p.bbox.intersects(clear_box):
                collisions.append(
                    Collision(
                        type="door_blocked",
                        severity="critical",
                        furniture_ids=[p.furniture_id],
                        description=(
                            f"{p.furniture_id} blocks {DOOR_CLEARANCE * 100:.0f}cm "
                            f"clearance zone of door_{i + 1} on {door.wall.value} wall "
                            f"(±{DOOR_SIDE_PAD * 100:.0f}cm side padding)"
                        ),
                    )
                )
    return collisions


_WALL_TOL = 0.15  # tolerance to consider an item "hugging" a wall


def _wall_side(bbox: AABB, room: RoomSpec) -> str | None:
    """Return which wall an item is hugging, or None if floating."""
    if bbox.min_x <= _WALL_TOL:
        return "west"
    if bbox.max_x >= room.width - _WALL_TOL:
        return "east"
    if bbox.min_z <= _WALL_TOL:
        return "south"
    if bbox.max_z >= room.depth - _WALL_TOL:
        return "north"
    return None


def _check_walkway_clearances(
    placements: list[PhysicalPlacement], room: RoomSpec | None = None
) -> list[Collision]:
    collisions: list[Collision] = []
    for i, a in enumerate(placements):
        for b in placements[i + 1 :]:
            if a.bbox.intersects(b.bbox):
                continue  # already reported as overlap
            dist = a.bbox.distance_to(b.bbox)
            if 0.0 < dist < WALKWAY_CLEARANCE:
                # Skip pairs where both items hug the SAME wall — the gap
                # between them is along the wall surface, not a walkway that
                # people need to pass through, so the clearance rule does not apply.
                if room is not None:
                    wall_a = _wall_side(a.bbox, room)
                    wall_b = _wall_side(b.bbox, room)
                    if wall_a is not None and wall_a == wall_b:
                        continue
                collisions.append(
                    Collision(
                        type="insufficient_clearance",
                        severity="major",
                        furniture_ids=[a.furniture_id, b.furniture_id],
                        description=(
                            f"{a.furniture_id} and {b.furniture_id} are {dist:.2f}m apart "
                            f"(minimum {WALKWAY_CLEARANCE}m required)"
                        ),
                    )
                )
    return collisions
