"""WallAssigner: pure-code wall assignment for furniture.

Replaces LLM spatial reasoning with deterministic rule-based logic.
Given a room spec (doors, windows, dimensions) and a list of furniture items,
assigns each item to a wall + alignment based on feng shui rules and
spatial constraints.

No LLM calls. All measurements in meters.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_ALL_WALLS = {"north", "south", "east", "west"}
_OPPOSITE_WALL = {"north": "south", "south": "north", "east": "west", "west": "east"}


# ---------------------------------------------------------------------------
# Furniture type sets
# ---------------------------------------------------------------------------

_REAL_BED_TYPES = {"bed"}
_SOFA_BED_TYPES = {"sofa_bed"}
_BED_LIKE_TYPES = _REAL_BED_TYPES | _SOFA_BED_TYPES

_SOFA_TYPES = {"sofa", "armchair"}
_DESK_TYPES = {"desk", "folding_desk"}
_WARDROBE_TYPES = {"wardrobe", "cabinet", "closet", "armoire", "compact_wardrobe"}
_SHELF_TYPES = {"bookshelf", "shelf"}
_STORAGE_TYPES = _WARDROBE_TYPES | _SHELF_TYPES

_NIGHTSTAND_TYPES = {"nightstand", "bedside_table", "lamp"}
_CENTER_TYPES = {"area_rug", "rug", "coffee_table", "ottoman", "pouffe", "room_divider"}
_DOOR_ADJACENT_TYPES = {"shoe_cabinet", "coat_rack"}
_TV_TYPES = {"tv_stand", "tv", "media_console"}
_SMALL_TYPES = {"plant", "mirror", "floor_lamp", "mini_fridge"}


def _normalize_type(furniture_type: str) -> str:
    """Normalize furniture_type to snake_case for matching."""
    return furniture_type.lower().replace("-", "_").replace(" ", "_")


def _wall_length(wall: str, room_width: float, room_depth: float) -> float:
    """Return the linear length of a wall."""
    if wall in ("north", "south"):
        return room_width
    return room_depth


class WallAssigner:
    """Assigns walls to furniture items using deterministic feng shui rules.

    Assignment order:
    1. bed → command position (opposite door, not window wall)
    2. nightstand → same wall as bed
    3. sofa_bed → command position (if no real bed) else side wall
    4. sofa → side wall opposite bed (not door wall)
    5. desk → side wall facing door (not door wall, not bed wall)
    6. tv_stand → wall opposite sofa/bed
    7. wardrobe → remaining wall (not bed wall, not door wall)
    8. bookshelf → remaining wall
    9. center items → center
    10. door-adjacent → door wall corners
    11. everything else → best remaining wall
    """

    def assign(
        self,
        furniture_items: list[dict[str, Any]],
        room_spec: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Assign wall/alignment/offset to each furniture item.

        Args:
            furniture_items: List of dicts with at least:
                furniture_id, furniture_type, size, priority
                (target_wall/alignment/offset_from_wall are IGNORED and overwritten)
            room_spec: Room spec with width, depth, doors, windows.

        Returns:
            The same list but with target_wall, alignment, offset_from_wall,
            and facing filled in by code.
        """
        dims = room_spec.get("dimensions") or {}
        room_w = float(room_spec.get("width") or dims.get("width") or 4.0)
        room_d = float(room_spec.get("depth") or dims.get("depth") or 4.0)

        door_walls = self._extract_walls(room_spec.get("doors", []))
        window_walls = self._extract_walls(room_spec.get("windows", []))

        # Track wall usage: wall → total width consumed
        wall_usage: dict[str, float] = {w: 0.0 for w in _ALL_WALLS}

        # Determine command wall (opposite primary door)
        primary_door_wall = next(iter(door_walls), "south")
        command_wall = _OPPOSITE_WALL.get(primary_door_wall, "north")

        # Bed valid walls: not door wall, not window wall
        bed_invalid = door_walls | window_walls
        bed_valid = _ALL_WALLS - bed_invalid
        # Prefer command wall for bed
        bed_wall = command_wall if command_wall in bed_valid else (
            next(iter(bed_valid)) if bed_valid else command_wall
        )

        # Sort by priority
        items = sorted(furniture_items, key=lambda x: x.get("priority", 99))

        # Pre-categorize
        assignments: dict[str, dict[str, Any]] = {}  # furniture_id → {wall, alignment, offset, facing}

        bed_assigned_wall: str | None = None
        sofa_assigned_wall: str | None = None
        desk_assigned_wall: str | None = None
        tv_assigned_wall: str | None = None

        # Pass 1: assign high-priority items
        for item in items:
            fid = item.get("furniture_id", item.get("id", ""))
            ft = _normalize_type(item.get("furniture_type", ""))
            fw = float(item.get("size", {}).get("w", item.get("width", 1.0)))

            if ft in _REAL_BED_TYPES:
                wall = bed_wall
                bed_assigned_wall = wall
                assignments[fid] = {
                    "target_wall": wall,
                    "alignment": "center",
                    "offset_from_wall": 0.05,
                    "facing": _OPPOSITE_WALL.get(wall, ""),
                }
                wall_usage[wall] += fw
                logger.info(f"WallAssigner: {fid} ({ft}) → {wall} wall (command position)")

            elif ft in _SOFA_BED_TYPES:
                # If no real bed, sofa_bed gets command position
                if not any(
                    _normalize_type(i.get("furniture_type", "")) in _REAL_BED_TYPES
                    for i in items
                ):
                    wall = bed_wall
                    bed_assigned_wall = wall
                else:
                    # Side wall, not door wall, not bed wall
                    wall = self._pick_wall(
                        exclude=door_walls | {bed_wall} if bed_wall else door_walls,
                        prefer_side=True,
                        room_w=room_w, room_d=room_d,
                        wall_usage=wall_usage, item_width=fw,
                    )
                assignments[fid] = {
                    "target_wall": wall,
                    "alignment": "center",
                    "offset_from_wall": 0.05,
                    "facing": _OPPOSITE_WALL.get(wall, ""),
                }
                wall_usage[wall] += fw
                if bed_assigned_wall is None:
                    bed_assigned_wall = wall
                logger.info(f"WallAssigner: {fid} ({ft}) → {wall} wall")

        # Pass 2: nightstands follow bed
        for item in items:
            fid = item.get("furniture_id", item.get("id", ""))
            if fid in assignments:
                continue
            ft = _normalize_type(item.get("furniture_type", ""))
            fw = float(item.get("size", {}).get("w", item.get("width", 0.5)))

            if ft in _NIGHTSTAND_TYPES and bed_assigned_wall:
                wall = bed_assigned_wall
                # Put nightstand beside bed: first one left, second one right
                existing_ns = sum(
                    1 for a in assignments.values()
                    if a["target_wall"] == wall
                    and any(
                        _normalize_type(i.get("furniture_type", "")) in _NIGHTSTAND_TYPES
                        for i in items
                        if (i.get("furniture_id", i.get("id", "")) in assignments
                            and assignments[i.get("furniture_id", i.get("id", ""))]["target_wall"] == wall)
                    )
                )
                align = "left" if existing_ns == 0 else "right"
                assignments[fid] = {
                    "target_wall": wall,
                    "alignment": align,
                    "offset_from_wall": 0.05,
                    "facing": "",
                }
                wall_usage[wall] += fw
                logger.info(f"WallAssigner: {fid} ({ft}) → {wall} wall (beside bed, {align})")

        # Pass 3: sofa, desk, tv, wardrobe, etc.
        for item in items:
            fid = item.get("furniture_id", item.get("id", ""))
            if fid in assignments:
                continue
            ft = _normalize_type(item.get("furniture_type", ""))
            fw = float(item.get("size", {}).get("w", item.get("width", 1.0)))

            if ft in _CENTER_TYPES:
                assignments[fid] = {
                    "target_wall": "center",
                    "alignment": "center",
                    "offset_from_wall": 0.0,
                    "facing": "",
                }
                logger.info(f"WallAssigner: {fid} ({ft}) → center")
                continue

            if ft in _DOOR_ADJACENT_TYPES:
                wall = primary_door_wall
                # Put near door corner
                existing_door = sum(
                    1 for a in assignments.values() if a["target_wall"] == wall
                )
                align = "left" if existing_door == 0 else "right"
                assignments[fid] = {
                    "target_wall": wall,
                    "alignment": align,
                    "offset_from_wall": 0.05,
                    "facing": "",
                }
                wall_usage[wall] += fw
                logger.info(f"WallAssigner: {fid} ({ft}) → {wall} wall (door adjacent, {align})")
                continue

            if ft in _SOFA_TYPES:
                exclude = door_walls.copy()
                if bed_assigned_wall:
                    exclude.add(bed_assigned_wall)
                wall = self._pick_wall(
                    exclude=exclude, prefer_side=True,
                    room_w=room_w, room_d=room_d,
                    wall_usage=wall_usage, item_width=fw,
                )
                sofa_assigned_wall = wall
                assignments[fid] = {
                    "target_wall": wall,
                    "alignment": "center",
                    "offset_from_wall": 0.1,
                    "facing": _OPPOSITE_WALL.get(wall, ""),
                }
                wall_usage[wall] += fw
                logger.info(f"WallAssigner: {fid} ({ft}) → {wall} wall")
                continue

            if ft in _DESK_TYPES:
                exclude = door_walls.copy()
                if bed_assigned_wall:
                    exclude.add(bed_assigned_wall)
                wall = self._pick_wall(
                    exclude=exclude, prefer_side=True,
                    room_w=room_w, room_d=room_d,
                    wall_usage=wall_usage, item_width=fw,
                )
                desk_assigned_wall = wall
                assignments[fid] = {
                    "target_wall": wall,
                    "alignment": "center",
                    "offset_from_wall": 0.05,
                    "facing": primary_door_wall,  # desk faces door
                }
                wall_usage[wall] += fw
                logger.info(f"WallAssigner: {fid} ({ft}) → {wall} wall (faces {primary_door_wall} door)")
                continue

            if ft in _TV_TYPES:
                # TV goes opposite sofa or bed
                ref_wall = sofa_assigned_wall or bed_assigned_wall
                if ref_wall:
                    wall = _OPPOSITE_WALL.get(ref_wall, "north")
                    if wall in door_walls:
                        wall = self._pick_wall(
                            exclude=door_walls | ({ref_wall} if ref_wall else set()),
                            prefer_side=False,
                            room_w=room_w, room_d=room_d,
                            wall_usage=wall_usage, item_width=fw,
                        )
                else:
                    wall = self._pick_wall(
                        exclude=door_walls,
                        prefer_side=False,
                        room_w=room_w, room_d=room_d,
                        wall_usage=wall_usage, item_width=fw,
                    )
                tv_assigned_wall = wall
                assignments[fid] = {
                    "target_wall": wall,
                    "alignment": "center",
                    "offset_from_wall": 0.05,
                    "facing": _OPPOSITE_WALL.get(wall, ""),
                }
                wall_usage[wall] += fw
                logger.info(f"WallAssigner: {fid} ({ft}) → {wall} wall (TV opposite viewing)")
                continue

            if ft in _STORAGE_TYPES:
                exclude = door_walls.copy()
                if bed_assigned_wall:
                    exclude.add(bed_assigned_wall)
                wall = self._pick_wall(
                    exclude=exclude, prefer_side=False,
                    room_w=room_w, room_d=room_d,
                    wall_usage=wall_usage, item_width=fw,
                )
                assignments[fid] = {
                    "target_wall": wall,
                    "alignment": self._pick_alignment(wall, wall_usage, fw, room_w, room_d),
                    "offset_from_wall": 0.0,
                    "facing": "",
                }
                wall_usage[wall] += fw
                logger.info(f"WallAssigner: {fid} ({ft}) → {wall} wall (storage)")
                continue

            # Default: small/misc items
            exclude = door_walls.copy()
            wall = self._pick_wall(
                exclude=exclude, prefer_side=False,
                room_w=room_w, room_d=room_d,
                wall_usage=wall_usage, item_width=fw,
            )
            assignments[fid] = {
                "target_wall": wall,
                "alignment": self._pick_alignment(wall, wall_usage, fw, room_w, room_d),
                "offset_from_wall": 0.05,
                "facing": "",
            }
            wall_usage[wall] += fw
            logger.info(f"WallAssigner: {fid} ({ft}) → {wall} wall (default)")

        # Apply assignments to items
        result = []
        for item in furniture_items:
            fid = item.get("furniture_id", item.get("id", ""))
            assignment = assignments.get(fid)
            if assignment:
                updated = dict(item)
                updated.update(assignment)
                result.append(updated)
            else:
                result.append(item)

        return result

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_walls(features: list[dict[str, Any]]) -> set[str]:
        """Extract wall names from door/window feature dicts."""
        walls: set[str] = set()
        for f in features:
            w = str(f.get("wall", "")).lower()
            if w and w in _ALL_WALLS:
                walls.add(w)
        return walls

    @staticmethod
    def _pick_wall(
        exclude: set[str],
        prefer_side: bool,
        room_w: float,
        room_d: float,
        wall_usage: dict[str, float],
        item_width: float,
    ) -> str:
        """Pick the best available wall based on remaining capacity.

        Args:
            exclude: Walls to avoid.
            prefer_side: If True, prefer east/west (side walls) over north/south.
            room_w: Room width.
            room_d: Room depth.
            wall_usage: Current width consumed per wall.
            item_width: Width of item to place.
        """
        candidates = _ALL_WALLS - exclude
        if not candidates:
            candidates = _ALL_WALLS  # fallback: use any wall

        def score(wall: str) -> float:
            length = _wall_length(wall, room_w, room_d)
            remaining = length - wall_usage.get(wall, 0.0)
            # Prefer walls with more remaining space
            s = remaining
            # Bonus for side walls if preferred
            if prefer_side and wall in ("east", "west"):
                s += 0.5
            # Penalty if item won't fit
            if remaining < item_width:
                s -= 10.0
            return s

        best = max(candidates, key=score)
        return best

    @staticmethod
    def _pick_alignment(
        wall: str,
        wall_usage: dict[str, float],
        item_width: float,
        room_w: float,
        room_d: float,
    ) -> str:
        """Pick alignment (left/center/right) based on wall usage."""
        used = wall_usage.get(wall, 0.0)
        length = _wall_length(wall, room_w, room_d)
        # If wall is mostly empty, center it
        if used < length * 0.3:
            return "left"
        elif used < length * 0.6:
            return "right"
        return "center"
