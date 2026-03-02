"""Hardcoded feng shui rule checker for resolved furniture placements.

Rules implemented (pure geometry, no LLM):
  - bed_not_facing_door
  - bed_headboard_solid_wall
  - desk_facing_door
  - wealth_corner_not_empty
  - mirror_not_facing_bed
  - no_bed_under_window

All measurements in meters.
Coordinate system: origin at SW corner, x=east, z=north.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.modules.layout.application.services.spatial_resolver import (
    PhysicalPlacement,
    RoomSpec,
)
from src.modules.layout.domain.entities.room import WallSide
from src.modules.layout.infrastructure.geometry.collision import AABB


@dataclass(frozen=True)
class FengShuiViolation:
    """Result of evaluating one feng shui rule.

    Attributes:
        rule_id: Unique rule identifier.
        passed: True if the rule is satisfied.
        severity: critical|major|minor (only meaningful when passed=False).
        suggestion: Human-readable remediation hint.
    """

    rule_id: str
    passed: bool
    severity: str
    suggestion: str


def check_feng_shui(
    placements: list[PhysicalPlacement],
    room: RoomSpec,
    direction: str = "south",
) -> list[FengShuiViolation]:
    """Evaluate all feng shui rules against the resolved layout.

    Args:
        placements: Output of SpatialResolver.resolve(). Furniture type is
                    inferred from the id prefix (e.g. "bed_01" → type "bed").
        room: Room dimensions and features.
        direction: Compass direction the main entrance faces (default "south").

    Returns:
        List of FengShuiViolation — one result per rule (always 6 items).
    """
    type_map = _build_type_map(placements)
    bed_p = _find_by_type(placements, "bed", type_map)
    desk_p = _find_by_type(placements, "desk", type_map)
    mirror_p = _find_by_type(placements, "mirror", type_map)

    return [
        _rule_bed_not_facing_door(bed_p, room),
        _rule_bed_headboard_solid_wall(bed_p, room),
        _rule_desk_facing_door(desk_p, room, placements),
        _rule_wealth_corner_not_empty(placements, room),
        _rule_mirror_not_facing_bed(mirror_p, bed_p),
        _rule_no_bed_under_window(bed_p, room),
    ]


# ---------------------------------------------------------------------------
# Individual rule implementations
# ---------------------------------------------------------------------------


def _rule_bed_not_facing_door(bed: PhysicalPlacement | None, room: RoomSpec) -> FengShuiViolation:
    rule_id = "bed_not_facing_door"
    if bed is None or not room.doors:
        return FengShuiViolation(
            rule_id=rule_id,
            passed=True,
            severity="minor",
            suggestion="No bed or door found; rule skipped.",
        )

    for door in room.doors:
        if door.wall == WallSide.SOUTH and bed.bbox.min_z < 1.0:
            return FengShuiViolation(
                rule_id=rule_id,
                passed=False,
                severity="critical",
                suggestion=(
                    "Move bed away from the south door — foot of bed is within 1m "
                    "of the door (coffin position). Place bed diagonally from door."
                ),
            )
        if door.wall == WallSide.NORTH and bed.bbox.max_z > room.depth - 1.0:
            return FengShuiViolation(
                rule_id=rule_id,
                passed=False,
                severity="critical",
                suggestion=(
                    "Move bed away from the north door — foot of bed is within 1m "
                    "of the door (coffin position)."
                ),
            )
        if door.wall == WallSide.WEST and bed.bbox.min_x < 1.0:
            return FengShuiViolation(
                rule_id=rule_id,
                passed=False,
                severity="critical",
                suggestion=(
                    "Move bed away from the west door — foot of bed is within 1m "
                    "of the door (coffin position)."
                ),
            )
        if door.wall == WallSide.EAST and bed.bbox.max_x > room.width - 1.0:
            return FengShuiViolation(
                rule_id=rule_id,
                passed=False,
                severity="critical",
                suggestion=(
                    "Move bed away from the east door — foot of bed is within 1m "
                    "of the door (coffin position)."
                ),
            )

    return FengShuiViolation(
        rule_id=rule_id,
        passed=True,
        severity="minor",
        suggestion="Bed is not in line with any door. Good.",
    )


def _rule_bed_headboard_solid_wall(
    bed: PhysicalPlacement | None, room: RoomSpec
) -> FengShuiViolation:
    rule_id = "bed_headboard_solid_wall"
    if bed is None:
        return FengShuiViolation(
            rule_id=rule_id, passed=True, severity="minor", suggestion="No bed found; rule skipped."
        )

    tolerance = 0.3
    rot = bed.rotation % 360

    if rot == 180:
        wall, near_wall = WallSide.SOUTH, bed.bbox.min_z < tolerance
        bed_span = (bed.bbox.min_x, bed.bbox.max_x)
    elif rot == 0:
        wall, near_wall = WallSide.NORTH, bed.bbox.max_z > room.depth - tolerance
        bed_span = (bed.bbox.min_x, bed.bbox.max_x)
    elif rot == 90:
        wall, near_wall = WallSide.WEST, bed.bbox.min_x < tolerance
        bed_span = (bed.bbox.min_z, bed.bbox.max_z)
    else:  # 270
        wall, near_wall = WallSide.EAST, bed.bbox.max_x > room.width - tolerance
        bed_span = (bed.bbox.min_z, bed.bbox.max_z)

    if not near_wall:
        return FengShuiViolation(
            rule_id=rule_id,
            passed=False,
            severity="major",
            suggestion=(
                f"Bed headboard is not against a wall. Place the headboard "
                f"against the {wall.value} wall for stability and support."
            ),
        )

    for window in room.windows:
        if window.wall != wall:
            continue
        if window.offset < bed_span[1] and window.offset + window.width > bed_span[0]:
            return FengShuiViolation(
                rule_id=rule_id,
                passed=False,
                severity="major",
                suggestion=(
                    "Bed headboard is against a wall with a window. "
                    "Move the bed to a solid wall without windows for better rest energy."
                ),
            )

    return FengShuiViolation(
        rule_id=rule_id,
        passed=True,
        severity="minor",
        suggestion="Bed headboard is against a solid wall. Good.",
    )


def _rule_desk_facing_door(
    desk: PhysicalPlacement | None,
    room: RoomSpec,
    all_placements: list[PhysicalPlacement],
) -> FengShuiViolation:
    rule_id = "desk_facing_door"
    if desk is None or not room.doors:
        return FengShuiViolation(
            rule_id=rule_id,
            passed=True,
            severity="minor",
            suggestion="No desk or door found; rule skipped.",
        )

    door = room.doors[0]
    desk_cx = (desk.bbox.min_x + desk.bbox.max_x) / 2.0
    desk_cz = (desk.bbox.min_z + desk.bbox.max_z) / 2.0
    door_cx = door.offset + door.width / 2.0

    if door.wall in (WallSide.SOUTH, WallSide.NORTH):
        door_x, door_z = door_cx, (0.0 if door.wall == WallSide.SOUTH else room.depth)
    else:
        door_x, door_z = (0.0 if door.wall == WallSide.WEST else room.width), door_cx

    line_box = _line_aabb(desk_cx, desk_cz, door_x, door_z, width=0.1)
    blocked = any(
        p.furniture_id != desk.furniture_id and p.bbox.intersects(line_box) for p in all_placements
    )

    if blocked:
        return FengShuiViolation(
            rule_id=rule_id,
            passed=False,
            severity="minor",
            suggestion=(
                "Desk does not have a clear line of sight to the door. "
                "Reposition desk so you can see the entrance while seated."
            ),
        )
    return FengShuiViolation(
        rule_id=rule_id,
        passed=True,
        severity="minor",
        suggestion="Desk has clear view of the door. Good.",
    )


def _rule_wealth_corner_not_empty(
    placements: list[PhysicalPlacement], room: RoomSpec
) -> FengShuiViolation:
    rule_id = "wealth_corner_not_empty"
    se_x = room.width * 0.6
    se_z = room.depth * 0.6

    for p in placements:
        cx = (p.bbox.min_x + p.bbox.max_x) / 2.0
        cz = (p.bbox.min_z + p.bbox.max_z) / 2.0
        if cx > se_x and cz > se_z:
            return FengShuiViolation(
                rule_id=rule_id,
                passed=True,
                severity="minor",
                suggestion="SE wealth corner contains furniture. Good.",
            )

    return FengShuiViolation(
        rule_id=rule_id,
        passed=False,
        severity="major",
        suggestion=(
            "The SE wealth corner (far right/back) is empty. "
            "Place a plant, lamp, or meaningful object there to activate prosperity energy."
        ),
    )


def _rule_mirror_not_facing_bed(
    mirror: PhysicalPlacement | None,
    bed: PhysicalPlacement | None,
) -> FengShuiViolation:
    rule_id = "mirror_not_facing_bed"
    if mirror is None or bed is None:
        return FengShuiViolation(
            rule_id=rule_id,
            passed=True,
            severity="minor",
            suggestion="No mirror or bed found; rule skipped.",
        )

    x_overlap = mirror.bbox.min_x < bed.bbox.max_x and mirror.bbox.max_x > bed.bbox.min_x
    if x_overlap:
        return FengShuiViolation(
            rule_id=rule_id,
            passed=False,
            severity="major",
            suggestion=(
                "Mirror is facing the bed. This disturbs sleep energy. "
                "Reposition mirror so it does not reflect the sleeping area."
            ),
        )
    return FengShuiViolation(
        rule_id=rule_id,
        passed=True,
        severity="minor",
        suggestion="Mirror does not face the bed. Good.",
    )


def _rule_no_bed_under_window(bed: PhysicalPlacement | None, room: RoomSpec) -> FengShuiViolation:
    rule_id = "no_bed_under_window"
    if bed is None:
        return FengShuiViolation(
            rule_id=rule_id, passed=True, severity="minor", suggestion="No bed found; rule skipped."
        )

    for window in room.windows:
        if window.wall in (WallSide.SOUTH, WallSide.NORTH):
            bed_min, bed_max = bed.bbox.min_x, bed.bbox.max_x
        else:
            bed_min, bed_max = bed.bbox.min_z, bed.bbox.max_z

        if window.offset < bed_max and window.offset + window.width > bed_min:
            return FengShuiViolation(
                rule_id=rule_id,
                passed=False,
                severity="major",
                suggestion=(
                    f"Bed is positioned under a window on the {window.wall.value} wall. "
                    "Move the bed to a solid wall to ensure stable energy and restful sleep."
                ),
            )

    return FengShuiViolation(
        rule_id=rule_id,
        passed=True,
        severity="minor",
        suggestion="Bed is not under any window. Good.",
    )


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------


def _build_type_map(placements: list[PhysicalPlacement]) -> dict[str, str]:
    return {p.furniture_id: p.furniture_id.split("_")[0] for p in placements}


def _find_by_type(
    placements: list[PhysicalPlacement],
    ftype: str,
    type_map: dict[str, str],
) -> PhysicalPlacement | None:
    return next((p for p in placements if type_map.get(p.furniture_id) == ftype), None)


def _line_aabb(x1: float, z1: float, x2: float, z2: float, width: float) -> AABB:
    """Approximate a line segment as a thin AABB for obstruction checking."""
    return AABB(
        min_x=min(x1, x2) - width / 2,
        min_z=min(z1, z2) - width / 2,
        max_x=max(x1, x2) + width / 2,
        max_z=max(z1, z2) + width / 2,
    )
