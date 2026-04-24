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

from src.modules.layout.application.services.kua_calculator import (
    calculate_kua,
    detect_kua_priority,
    kua_auspicious_walls,
    kua_best_direction_info,
    kua_inauspicious_walls,
)

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
_DINING_CHAIR_TYPES = {"dining_chair"}


_COMPOUND_TYPES: dict[tuple[str, str], str] = {
    ("sofa", "bed"): "sofa_bed",
    ("tv", "stand"): "tv_stand",
    ("coffee", "table"): "coffee_table",
    ("office", "chair"): "office_chair",
    ("dining", "chair"): "dining_chair",
    ("dining", "table"): "dining_table",
    ("shoe", "cabinet"): "shoe_cabinet",
    ("coat", "rack"): "coat_rack",
    ("room", "divider"): "room_divider",
    ("compact", "wardrobe"): "compact_wardrobe",
    ("folding", "desk"): "folding_desk",
    ("area", "rug"): "area_rug",
    ("floor", "lamp"): "floor_lamp",
    ("mini", "fridge"): "mini_fridge",
}


def _normalize_type(furniture_type: str, furniture_id: str = "") -> str:
    """Normalize furniture_type to snake_case for matching.

    If furniture_type looks incomplete (single token that is a known prefix),
    attempt to derive the full compound type from furniture_id tokens.
    """
    import re

    normalized = furniture_type.lower().replace("-", "_").replace(" ", "_")

    # If type already looks complete (contains underscore or is multi-word), return as-is
    if "_" in normalized:
        return normalized

    # Try to derive compound type from furniture_id
    if furniture_id:
        tokens = re.split(r"[-_\s]+", furniture_id.lower())
        if len(tokens) >= 2 and (tokens[0], tokens[1]) in _COMPOUND_TYPES:
            return _COMPOUND_TYPES[(tokens[0], tokens[1])]

    return normalized


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

    def compute_valid_walls(
        self,
        furniture_items: list[dict[str, Any]],
        room_spec: dict[str, Any],
    ) -> dict[str, dict[str, Any]]:
        """Compute valid, preferred, and forbidden walls for each furniture item.

        Returns a dict of furniture_id → {
            "valid_walls": list[str],    # walls LLM may choose from
            "preferred": str,            # Kua/command best wall
            "forbidden": list[str],      # walls that violate hard rules
            "reason": str,               # explanation for LLM
        }
        Used by LLM to make informed wall selections while respecting hard constraints.
        """
        dims = room_spec.get("dimensions") or {}
        room_w = float(room_spec.get("width") or dims.get("width") or 4.0)
        room_d = float(room_spec.get("depth") or dims.get("depth") or 4.0)

        door_walls = self._extract_walls(room_spec.get("doors", []))
        window_walls = self._extract_walls(room_spec.get("windows", []))

        primary_door_wall = next(iter(door_walls), "south")
        command_wall = _OPPOSITE_WALL.get(primary_door_wall, "north")

        # Kua walls
        user_prefs = room_spec.get("user_preferences") or {}
        birth_year = user_prefs.get("birth_year")
        gender = user_prefs.get("gender", "")
        user_message = user_prefs.get("user_message", "")
        kua_walls: list[str] = []
        kua_bad: set[str] = set()
        kua_num = None
        kua_priority = "sheng_chi"
        if birth_year and gender:
            try:
                kua_num = calculate_kua(int(birth_year), gender)
                kua_priority = detect_kua_priority(user_message)
                priority_info = kua_best_direction_info(kua_num, kua_priority)
                priority_wall = priority_info["wall"]
                kua_walls = [priority_wall] + [
                    w for w in kua_auspicious_walls(kua_num) if w != priority_wall
                ]
                kua_bad = kua_inauspicious_walls(kua_num)
            except Exception:
                pass

        result: dict[str, dict[str, Any]] = {}
        wall_usage: dict[str, float] = dict.fromkeys(_ALL_WALLS, 0.0)

        items = sorted(furniture_items, key=lambda x: x.get("priority", 99))
        bed_assigned_wall: str | None = None
        sofa_assigned_wall: str | None = None

        for item in items:
            fid = item.get("furniture_id", item.get("id", ""))
            ft = _normalize_type(item.get("furniture_type", ""), fid)
            fw = float(item.get("size", {}).get("w", item.get("width", 1.0)))

            # Center items — no wall choice
            if ft in _CENTER_TYPES:
                result[fid] = {
                    "valid_walls": ["center"],
                    "preferred": "center",
                    "forbidden": [],
                    "reason": "วางกลางห้อง",
                }
                continue

            # Door-adjacent items
            if ft in _DOOR_ADJACENT_TYPES:
                result[fid] = {
                    "valid_walls": [primary_door_wall],
                    "preferred": primary_door_wall,
                    "forbidden": list(_ALL_WALLS - {primary_door_wall}),
                    "reason": "ต้องวางชิดประตู",
                }
                continue

            # Nightstand — must follow bed
            if ft in _NIGHTSTAND_TYPES:
                wall = bed_assigned_wall or command_wall
                result[fid] = {
                    "valid_walls": [wall],
                    "preferred": wall,
                    "forbidden": list(_ALL_WALLS - {wall}),
                    "reason": "ต้องวางผนังเดียวกับเตียง",
                }
                continue

            # Dining chair — must follow dining table
            if ft in _DINING_CHAIR_TYPES:
                result[fid] = {
                    "valid_walls": list(_ALL_WALLS - door_walls),
                    "preferred": command_wall,
                    "forbidden": list(door_walls),
                    "reason": "วางข้างโต๊ะอาหาร ห้ามผนังประตู",
                }
                continue

            # Bed
            if ft in _REAL_BED_TYPES:
                forbidden = list(door_walls)
                # valid = all except door walls; window walls soft-invalid but allowed
                valid = sorted(_ALL_WALLS - door_walls)
                # preferred: Kua first, then command
                preferred = kua_walls[0] if kua_walls else command_wall
                reason_parts = []
                if kua_walls:
                    reason_parts.append(f"Kua {kua_num} ({kua_priority}) แนะนำ {kua_walls[0]}")
                reason_parts.append(f"command position = {command_wall}")
                if window_walls:
                    reason_parts.append(f"หลีกเลี่ยงผนังหน้าต่าง {sorted(window_walls)} ถ้าเป็นไปได้")
                if kua_bad:
                    reason_parts.append(f"ทิศอัปมงคล Kua = {sorted(kua_bad)}")
                result[fid] = {
                    "valid_walls": valid,
                    "preferred": preferred,
                    "forbidden": forbidden,
                    "kua_avoid": sorted(kua_bad),
                    "window_walls": sorted(window_walls),
                    "reason": " | ".join(reason_parts),
                }
                bed_assigned_wall = preferred
                wall_usage[preferred] = wall_usage.get(preferred, 0.0) + fw
                continue

            # Sofa bed
            if ft in _SOFA_BED_TYPES:
                has_real_bed = any(
                    _normalize_type(i.get("furniture_type", "")) in _REAL_BED_TYPES for i in items
                )
                if not has_real_bed:
                    forbidden = list(door_walls)
                    valid = sorted(_ALL_WALLS - door_walls)
                    preferred = kua_walls[0] if kua_walls else command_wall
                else:
                    forbidden = list(door_walls | ({bed_assigned_wall} if bed_assigned_wall else set()))
                    valid = sorted(_ALL_WALLS - set(forbidden))
                    preferred = valid[0] if valid else command_wall
                result[fid] = {
                    "valid_walls": valid or list(_ALL_WALLS - door_walls),
                    "preferred": preferred,
                    "forbidden": forbidden,
                    "reason": "sofa_bed: command position ถ้าไม่มีเตียง หรือผนังข้างถ้ามีเตียงแล้ว",
                }
                sofa_assigned_wall = preferred
                wall_usage[preferred] = wall_usage.get(preferred, 0.0) + fw
                continue

            # Sofa
            if ft in _SOFA_TYPES:
                exclude = door_walls.copy()
                if bed_assigned_wall:
                    exclude.add(bed_assigned_wall)
                valid = sorted(_ALL_WALLS - exclude)
                preferred = valid[0] if valid else sorted(_ALL_WALLS - door_walls)[0]
                result[fid] = {
                    "valid_walls": valid or sorted(_ALL_WALLS - door_walls),
                    "preferred": preferred,
                    "forbidden": list(exclude),
                    "reason": "โซฟา: ผนังข้าง ห้ามผนังประตูและผนังเตียง",
                }
                sofa_assigned_wall = preferred
                wall_usage[preferred] = wall_usage.get(preferred, 0.0) + fw
                continue

            # Desk
            if ft in _DESK_TYPES:
                exclude = door_walls.copy()
                if bed_assigned_wall:
                    exclude.add(bed_assigned_wall)
                if sofa_assigned_wall:
                    exclude.add(sofa_assigned_wall)
                valid = sorted(_ALL_WALLS - exclude)
                if not valid:
                    valid = sorted(_ALL_WALLS - door_walls)
                # No fixed preferred — let LLM choose freely from valid_walls
                result[fid] = {
                    "valid_walls": valid,
                    "preferred": "",
                    "forbidden": list(door_walls | (({bed_assigned_wall} if bed_assigned_wall else set()))),
                    "reason": "โต๊ะทำงาน: เลือกผนังที่ยังไม่แออัด ห้ามผนังประตูและผนังเตียง",
                }
                wall_usage[valid[0] if valid else command_wall] = wall_usage.get(valid[0] if valid else command_wall, 0.0) + fw
                continue

            # TV stand
            if ft in _TV_TYPES:
                ref_wall = sofa_assigned_wall or bed_assigned_wall
                occupied = door_walls | {a for a in [bed_assigned_wall, sofa_assigned_wall] if a}
                if ref_wall:
                    preferred = _OPPOSITE_WALL.get(ref_wall, "north")
                    if preferred in occupied:
                        valid = sorted(_ALL_WALLS - occupied)
                        preferred = valid[0] if valid else preferred
                valid_walls = sorted(_ALL_WALLS - occupied) or sorted(_ALL_WALLS - door_walls)
                result[fid] = {
                    "valid_walls": valid_walls,
                    "preferred": preferred if ref_wall else (valid_walls[0] if valid_walls else "north"),
                    "forbidden": list(door_walls),
                    "reason": "TV: ตรงข้ามโซฟา/เตียง เพื่อมุมมองที่ดี",
                }
                wall_usage[preferred if ref_wall else valid_walls[0]] = wall_usage.get(preferred if ref_wall else valid_walls[0], 0.0) + fw
                continue

            # Storage (wardrobe, bookshelf)
            if ft in _STORAGE_TYPES:
                exclude = door_walls.copy()
                if bed_assigned_wall:
                    exclude.add(bed_assigned_wall)
                if sofa_assigned_wall:
                    exclude.add(sofa_assigned_wall)
                valid = sorted(_ALL_WALLS - exclude)
                if not valid:
                    valid = sorted(_ALL_WALLS - door_walls)
                # No fixed preferred — let LLM choose freely from valid_walls
                result[fid] = {
                    "valid_walls": valid,
                    "preferred": "",
                    "forbidden": list(exclude),
                    "reason": "ตู้เก็บของ: เลือกผนังที่ยังไม่แออัด ห้ามผนังเตียง/ประตู",
                }
                wall_usage[valid[0] if valid else "east"] = wall_usage.get(valid[0] if valid else "east", 0.0) + fw
                continue

            # Default
            exclude = door_walls | ({bed_assigned_wall} if bed_assigned_wall else set())
            valid = sorted(_ALL_WALLS - exclude)
            if not valid:
                valid = sorted(_ALL_WALLS - door_walls)
            preferred = valid[0] if valid else "east"
            result[fid] = {
                "valid_walls": valid,
                "preferred": preferred,
                "forbidden": list(door_walls),
                "reason": "เฟอร์นิเจอร์ทั่วไป: ผนังที่เหลือ",
            }
            wall_usage[preferred] = wall_usage.get(preferred, 0.0) + fw

        return result

    def assign(
        self,
        furniture_items: list[dict[str, Any]],
        room_spec: dict[str, Any],
        llm_walls: dict[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        """Assign wall/alignment/offset to each furniture item.

        Args:
            furniture_items: List of dicts with at least:
                furniture_id, furniture_type, size, priority.
            room_spec: Room spec with width, depth, doors, windows.
            llm_walls: Optional dict of furniture_id → wall chosen by LLM.
                When provided, the LLM's wall choice is used instead of the
                deterministic pick for that item (alignment/offset/facing are
                still computed by code). Hard constraints (center/door-adjacent
                types) always override llm_walls.

        Returns:
            The same list but with target_wall, alignment, offset_from_wall,
            and facing filled in by code.
        """
        llm_walls = llm_walls or {}
        dims = room_spec.get("dimensions") or {}
        room_w = float(room_spec.get("width") or dims.get("width") or 4.0)
        room_d = float(room_spec.get("depth") or dims.get("depth") or 4.0)

        door_walls = self._extract_walls(room_spec.get("doors", []))
        window_walls = self._extract_walls(room_spec.get("windows", []))

        # Track wall usage: wall → total width consumed
        wall_usage: dict[str, float] = dict.fromkeys(_ALL_WALLS, 0.0)

        # Determine command wall (opposite primary door)
        primary_door_wall = next(iter(door_walls), "south")
        command_wall = _OPPOSITE_WALL.get(primary_door_wall, "north")

        # Bed constraints:
        # Rule: bed must NOT be in direct door axis (ตรงกับประตู) — but CAN be on same wall
        # as long as it's offset. WallAssigner works at wall level, not coordinate level,
        # so we treat door wall as soft-invalid (prefer to avoid, but Kua can override).
        # The spatial_resolver and clearance checker enforce the actual axis constraint.
        bed_soft_invalid = window_walls | door_walls  # prefer to avoid, but overridable
        bed_valid_strict = _ALL_WALLS - bed_soft_invalid
        bed_valid_kua_override = _ALL_WALLS  # Kua can place on any wall

        # Kua-based preferred wall for bed headboard (highest priority)
        user_prefs = room_spec.get("user_preferences") or {}
        birth_year = user_prefs.get("birth_year")
        gender = user_prefs.get("gender", "")
        user_message = user_prefs.get("user_message", "")
        kua_walls: list[str] = []
        if birth_year and gender:
            try:
                kua = calculate_kua(int(birth_year), gender)
                priority = detect_kua_priority(user_message)
                # Put priority direction first, then remaining auspicious walls as fallback
                priority_info = kua_best_direction_info(kua, priority)
                priority_wall = priority_info["wall"]
                kua_walls = [priority_wall] + [
                    w for w in kua_auspicious_walls(kua) if w != priority_wall
                ]
                kua_bad = kua_inauspicious_walls(kua)
                logger.info(
                    f"WallAssigner: Kua={kua} (birth={birth_year}, gender={gender}) "
                    f"priority={priority} → {priority_wall}, auspicious_walls={kua_walls[:4]} inauspicious={kua_bad}"
                )
            except Exception as e:
                logger.warning(f"WallAssigner: Kua calculation failed: {e}")

        # Pick bed wall:
        # Priority 1: Kua auspicious wall (even if window wall — Kua overrides feng shui)
        # Priority 2: feng shui valid wall (no door, no window)
        # Priority 3: any non-door wall
        bed_wall = command_wall  # fallback
        if kua_walls:
            # Try Kua walls — only exclude door wall (hard constraint)
            for w in kua_walls:
                if w in bed_valid_kua_override:
                    bed_wall = w
                    if w in bed_soft_invalid:
                        logger.info(
                            f"WallAssigner: bed wall set by Kua → {w} (overrides window rule)"
                        )
                    else:
                        logger.info(f"WallAssigner: bed wall set by Kua → {w}")
                    break
            else:
                # All Kua walls unavailable — fall back to command wall
                bed_wall = (
                    command_wall
                    if command_wall in bed_valid_strict
                    else (next(iter(bed_valid_strict)) if bed_valid_strict else command_wall)
                )
        else:
            # No Kua data — prefer no-door, no-window wall; command wall is best
            bed_wall = (
                command_wall
                if command_wall in bed_valid_strict
                else (next(iter(bed_valid_strict)) if bed_valid_strict else command_wall)
            )

        # Sort by priority
        items = sorted(furniture_items, key=lambda x: x.get("priority", 99))

        # Pre-categorize
        assignments: dict[
            str, dict[str, Any]
        ] = {}  # furniture_id → {wall, alignment, offset, facing}

        bed_assigned_wall: str | None = None
        sofa_assigned_wall: str | None = None
        dining_table_wall: str | None = None
        storage_assigned_wall: str | None = None

        # Pass 1: assign high-priority items
        for item in items:
            fid = item.get("furniture_id", item.get("id", ""))
            ft = _normalize_type(item.get("furniture_type", ""), fid)
            fw = float(item.get("size", {}).get("w", item.get("width", 1.0)))

            if ft in _REAL_BED_TYPES:
                # Kua has highest priority for bed — LLM is only used when no Kua data
                llm_choice = llm_walls.get(fid)
                if kua_walls:
                    # Kua overrides LLM — bed must follow auspicious direction
                    wall = bed_wall
                    if llm_choice and llm_choice != wall:
                        logger.info(
                            f"WallAssigner: {fid} LLM wall={llm_choice!r} overridden by Kua → {wall!r}"
                        )
                    else:
                        logger.info(f"WallAssigner: {fid} using Kua wall={wall!r}")
                else:
                    # No Kua data — respect LLM choice if not a door wall
                    wall = (
                        llm_choice
                        if llm_choice and llm_choice in (_ALL_WALLS - door_walls)
                        else bed_wall
                    )
                    if llm_choice and llm_choice != wall:
                        logger.info(f"WallAssigner: {fid} LLM wall={llm_choice!r} rejected (door wall) → {wall!r}")
                    elif llm_choice:
                        logger.info(f"WallAssigner: {fid} using LLM wall={wall!r}")
                bed_assigned_wall = wall
                # If bed shares a wall with a door, slide it away from the door
                bed_align = "center"
                doors_on_wall = [
                    d for d in room_spec.get("doors", []) if str(d.get("wall", "")).lower() == wall
                ]
                if doors_on_wall:
                    door = doors_on_wall[0]
                    door_off = float(door.get("offset", 0.0))
                    door_w = float(door.get("width", 0.9))
                    wall_len = _wall_length(wall, room_w, room_d)
                    # Space on each side of the door
                    left_space = door_off
                    right_space = wall_len - (door_off + door_w)
                    bed_align = "right" if right_space >= left_space else "left"
                    logger.info(
                        f"WallAssigner: bed shares {wall} wall with door → align={bed_align} "
                        f"(left_space={left_space:.2f}, right_space={right_space:.2f})"
                    )
                assignments[fid] = {
                    "target_wall": wall,
                    "alignment": bed_align,
                    "offset_from_wall": 0.0,
                    "facing": _OPPOSITE_WALL.get(wall, ""),
                }
                wall_usage[wall] += fw
                logger.info(f"WallAssigner: {fid} ({ft}) → {wall} wall (command position)")

            elif ft in _SOFA_BED_TYPES:
                # If no real bed, sofa_bed gets command position (Kua overrides LLM)
                llm_choice = llm_walls.get(fid)
                if not any(
                    _normalize_type(i.get("furniture_type", "")) in _REAL_BED_TYPES for i in items
                ):
                    if kua_walls:
                        wall = bed_wall
                        if llm_choice and llm_choice != wall:
                            logger.info(
                                f"WallAssigner: {fid} LLM wall={llm_choice!r} overridden by Kua → {wall!r}"
                            )
                    else:
                        wall = (
                            llm_choice
                            if llm_choice and llm_choice in (_ALL_WALLS - door_walls)
                            else bed_wall
                        )
                    bed_assigned_wall = wall
                else:
                    # Side wall, not door wall, not bed wall
                    _sb_exclude = door_walls | {bed_wall} if bed_wall else door_walls
                    if llm_choice and llm_choice not in _sb_exclude:
                        wall = llm_choice
                        logger.info(f"WallAssigner: {fid} using LLM wall={wall!r}")
                    else:
                        wall = self._pick_wall(
                            exclude=_sb_exclude,
                            prefer_side=True,
                            room_w=room_w,
                            room_d=room_d,
                            wall_usage=wall_usage,
                            item_width=fw,
                        )
                assignments[fid] = {
                    "target_wall": wall,
                    "alignment": "center",
                    "offset_from_wall": 0.0,
                    "facing": _OPPOSITE_WALL.get(wall, ""),
                }
                wall_usage[wall] += fw
                sofa_assigned_wall = wall
                if bed_assigned_wall is None:
                    bed_assigned_wall = wall
                logger.info(f"WallAssigner: {fid} ({ft}) → {wall} wall")

        # Pass 2: nightstands follow bed
        for item in items:
            fid = item.get("furniture_id", item.get("id", ""))
            if fid in assignments:
                continue
            ft = _normalize_type(item.get("furniture_type", ""), fid)
            fw = float(item.get("size", {}).get("w", item.get("width", 0.5)))

            if ft in _NIGHTSTAND_TYPES and bed_assigned_wall:
                wall = bed_assigned_wall
                # Nightstand goes beside bed on the same wall.
                # Find the bed item to figure out which side has more room.
                bed_item = next(
                    (i for i in items if _normalize_type(i.get("furniture_type", ""), i.get("furniture_id", i.get("id", ""))) in _REAL_BED_TYPES),
                    None,
                )
                bed_w = float(bed_item.get("size", {}).get("w", 1.6)) if bed_item else 1.6
                bed_l = float(bed_item.get("size", {}).get("l", 2.0)) if bed_item else 2.0
                wall_len = _wall_length(wall, room_w, room_d)
                # Axis size of bed along the wall (west/east → z axis = bed_l; north/south → x axis = bed_w)
                bed_axis = bed_l if wall in ("west", "east") else bed_w
                bed_start = (wall_len - bed_axis) / 2.0  # bed is center-aligned

                existing_ns = [a for a in assignments.values() if a["target_wall"] == wall and a.get("_is_nightstand")]

                # Compute exact z position along wall so nightstand sits beside bed.
                # bed is center-aligned → bed occupies z=[bed_start, bed_start+bed_axis]
                bed_end = bed_start + bed_axis
                if not existing_ns:
                    # First nightstand: place on the side with more room
                    left_room = bed_start
                    right_room = wall_len - bed_end
                    if left_room >= fw:
                        align = "left"
                        ns_z = max(0.0, bed_start - fw)
                    elif right_room >= fw:
                        align = "right"
                        ns_z = min(wall_len - fw, bed_end)
                    else:
                        align = "left"
                        ns_z = max(0.0, bed_start - fw)
                else:
                    prev_align = existing_ns[0]["alignment"]
                    if prev_align == "left":
                        align = "right"
                        ns_z = min(wall_len - fw, bed_end)
                    else:
                        align = "left"
                        ns_z = max(0.0, bed_start - fw)

                assignments[fid] = {
                    "target_wall": wall,
                    "alignment": align,
                    "offset_from_wall": 0.0,
                    "facing": "",
                    "_is_nightstand": True,
                    "along_wall_z": ns_z,
                }
                wall_usage[wall] += fw
                logger.info(f"WallAssigner: {fid} ({ft}) → {wall} wall (beside bed, {align}, z={ns_z:.2f})")

        # Pass 3: sofa, desk, tv, wardrobe, etc.
        for item in items:
            fid = item.get("furniture_id", item.get("id", ""))
            if fid in assignments:
                continue
            ft = _normalize_type(item.get("furniture_type", ""), fid)
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
                wall_len = _wall_length(wall, room_w, room_d)
                # Find primary door info to check available space on each side
                primary_door = next(
                    (
                        d
                        for d in room_spec.get("doors", [])
                        if str(d.get("wall", "")).lower() == wall
                    ),
                    None,
                )
                _GAP = 0.15
                if primary_door:
                    door_off = float(primary_door.get("offset", 0.0))
                    door_w = float(primary_door.get("width", 0.9))
                    left_space = door_off - _GAP
                    right_space = wall_len - (door_off + door_w + _GAP)
                    # Determine which side has been used already
                    existing_door_items = [
                        a
                        for a in assignments.values()
                        if a["target_wall"] == wall and a.get("_door_side")
                    ]
                    used_left = any(a.get("_door_side") == "left" for a in existing_door_items)
                    used_right = any(a.get("_door_side") == "right" for a in existing_door_items)
                    # Pick side: prefer left if fits, else right if fits
                    if not used_left and left_space >= fw:
                        align = "left"
                    elif not used_right and right_space >= fw:
                        align = "right"
                    elif left_space >= fw:
                        align = "left"
                    else:
                        align = "right"
                else:
                    existing_door = sum(1 for a in assignments.values() if a["target_wall"] == wall)
                    align = "left" if existing_door == 0 else "right"
                assignments[fid] = {
                    "target_wall": wall,
                    "alignment": align,
                    "offset_from_wall": 0.05,
                    "facing": "",
                    "_door_side": align,
                }
                wall_usage[wall] += fw
                logger.info(f"WallAssigner: {fid} ({ft}) → {wall} wall (door adjacent, {align})")
                continue

            if ft in _SOFA_TYPES:
                exclude = door_walls.copy()
                if bed_assigned_wall:
                    exclude.add(bed_assigned_wall)
                if sofa_assigned_wall:
                    exclude.add(sofa_assigned_wall)
                llm_choice = llm_walls.get(fid)
                if llm_choice and llm_choice not in exclude:
                    wall = llm_choice
                    logger.info(f"WallAssigner: {fid} using LLM wall={wall!r}")
                else:
                    wall = self._pick_wall(
                        exclude=exclude,
                        prefer_side=True,
                        room_w=room_w,
                        room_d=room_d,
                        wall_usage=wall_usage,
                        item_width=fw,
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
                if sofa_assigned_wall:
                    exclude.add(sofa_assigned_wall)
                if storage_assigned_wall:
                    exclude.add(storage_assigned_wall)
                if dining_table_wall:
                    exclude.add(dining_table_wall)
                if exclude >= _ALL_WALLS:
                    exclude = door_walls.copy()  # fallback
                llm_choice = llm_walls.get(fid)
                if llm_choice and llm_choice not in exclude:
                    wall = llm_choice
                    logger.info(f"WallAssigner: {fid} using LLM wall={wall!r}")
                else:
                    if llm_choice and llm_choice in exclude:
                        logger.info(
                            f"WallAssigner: {fid} LLM wall={llm_choice!r} conflicts with bed/door → picking alternate"
                        )
                    wall = self._pick_wall(
                        exclude=exclude,
                        prefer_side=True,
                        room_w=room_w,
                        room_d=room_d,
                        wall_usage=wall_usage,
                        item_width=fw,
                    )
                assignments[fid] = {
                    "target_wall": wall,
                    "alignment": "center",
                    "offset_from_wall": 0.05,
                    "facing": primary_door_wall,  # desk faces door
                }
                wall_usage[wall] += fw
                logger.info(
                    f"WallAssigner: {fid} ({ft}) → {wall} wall (faces {primary_door_wall} door)"
                )
                continue

            if ft in _TV_TYPES:
                # TV goes opposite sofa (viewing direction); fallback to opposite bed
                ref_wall = sofa_assigned_wall or bed_assigned_wall
                # All walls already occupied by furniture — TV must not share these
                occupied_walls = {
                    a["target_wall"] for a in assignments.values() if a["target_wall"] != "center"
                }
                occupied = door_walls | occupied_walls
                llm_choice = llm_walls.get(fid)
                if llm_choice and llm_choice not in door_walls and llm_choice in _ALL_WALLS:
                    wall = llm_choice
                    logger.info(f"WallAssigner: {fid} using LLM wall={wall!r}")
                elif ref_wall:
                    wall = _OPPOSITE_WALL.get(ref_wall, "north")
                    if wall in occupied:
                        wall = self._pick_wall(
                            exclude=occupied | ({ref_wall} if ref_wall else set()),
                            prefer_side=False,
                            room_w=room_w,
                            room_d=room_d,
                            wall_usage=wall_usage,
                            item_width=fw,
                        )
                else:
                    wall = self._pick_wall(
                        exclude=occupied,
                        prefer_side=False,
                        room_w=room_w,
                        room_d=room_d,
                        wall_usage=wall_usage,
                        item_width=fw,
                    )
                tv_align = (
                    self._safe_alignment_for_door_wall(
                        wall, fw, room_w, room_d, room_spec.get("doors", [])
                    )
                    if wall in door_walls
                    else "center"
                )
                assignments[fid] = {
                    "target_wall": wall,
                    "alignment": tv_align,
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
                if sofa_assigned_wall:
                    exclude.add(sofa_assigned_wall)
                # Exclude crowded walls (usage > 60% of wall length)
                _CROWDED_THRESHOLD = 0.6
                crowded_walls = {
                    w for w in _ALL_WALLS
                    if wall_usage.get(w, 0.0) > _wall_length(w, room_w, room_d) * _CROWDED_THRESHOLD
                }
                exclude_storage = exclude | crowded_walls
                # If all non-door walls are crowded, allow door wall (spatial_resolver
                # will use _safe_alignment to place beside the door, not in front of it)
                if exclude_storage >= _ALL_WALLS:
                    exclude_storage = exclude | crowded_walls - door_walls
                if exclude_storage >= _ALL_WALLS:
                    exclude_storage = exclude  # absolute fallback
                llm_choice = llm_walls.get(fid)
                if llm_choice and llm_choice not in exclude and llm_choice in _ALL_WALLS:
                    wall = llm_choice
                    logger.info(f"WallAssigner: {fid} using LLM wall={wall!r}")
                else:
                    wall = self._pick_wall(
                        exclude=exclude_storage,
                        prefer_side=False,
                        room_w=room_w,
                        room_d=room_d,
                        wall_usage=wall_usage,
                        item_width=fw,
                    )
                align = (
                    self._safe_alignment_for_door_wall(
                        wall, fw, room_w, room_d, room_spec.get("doors", [])
                    )
                    if wall in door_walls
                    else self._pick_alignment(wall, wall_usage, fw, room_w, room_d)
                )
                assignments[fid] = {
                    "target_wall": wall,
                    "alignment": align,
                    "offset_from_wall": 0.0,
                    "facing": "",
                }
                wall_usage[wall] += fw
                if ft == "dining_table":
                    dining_table_wall = wall
                elif ft in _WARDROBE_TYPES | _SHELF_TYPES:
                    if storage_assigned_wall is None:
                        storage_assigned_wall = wall
                logger.info(f"WallAssigner: {fid} ({ft}) → {wall} wall (storage)")
                continue

            if ft in _DINING_CHAIR_TYPES:
                if dining_table_wall:
                    wall = dining_table_wall
                    assignments[fid] = {
                        "target_wall": wall,
                        "alignment": "center",
                        "offset_from_wall": 0.05,
                        "facing": "",
                    }
                    wall_usage[wall] += fw
                    logger.info(f"WallAssigner: {fid} ({ft}) → {wall} wall (beside dining table)")
                    continue

            if ft == "dining_table":
                # dining_table: always center-aligned against a wall.
                # Must NOT share a wall with wardrobe/storage — they compete for the
                # same wall space and bump each other out.
                logger.info(
                    f"WallAssigner: dining_table exclude: bed={bed_assigned_wall} "
                    f"sofa={sofa_assigned_wall} storage={storage_assigned_wall} door={door_walls}"
                )
                # Try progressively relaxed constraints until a free wall is found:
                # 1. Ideal: avoid door, bed, sofa, storage
                # 2. Allow door wall (placed beside door, not in front)
                # 3. Allow storage wall (share wall, _bump_out slides apart)
                # 4. Any wall (absolute fallback)
                _dt_hard = set()
                if bed_assigned_wall:
                    _dt_hard.add(bed_assigned_wall)
                if sofa_assigned_wall:
                    _dt_hard.add(sofa_assigned_wall)

                exclude_dt: set[str]
                if _dt_hard | door_walls | {storage_assigned_wall} - {None} < _ALL_WALLS:
                    exclude_dt = door_walls | _dt_hard
                    if storage_assigned_wall:
                        exclude_dt.add(storage_assigned_wall)
                elif _dt_hard | {storage_assigned_wall} - {None} < _ALL_WALLS:
                    # Allow door wall
                    exclude_dt = _dt_hard.copy()
                    if storage_assigned_wall:
                        exclude_dt.add(storage_assigned_wall)
                elif _dt_hard < _ALL_WALLS:
                    # Allow door wall + storage wall (share with wardrobe)
                    exclude_dt = _dt_hard.copy()
                else:
                    exclude_dt = set()  # all walls taken — pick best by capacity
                wall = self._pick_wall(
                    exclude=exclude_dt,
                    prefer_side=False,
                    room_w=room_w,
                    room_d=room_d,
                    wall_usage=wall_usage,
                    item_width=fw,
                )
                # Always center on its wall so it doesn't end up stuck in a corner
                align = (
                    self._safe_alignment_for_door_wall(
                        wall, fw, room_w, room_d, room_spec.get("doors", [])
                    )
                    if wall in door_walls
                    else "center"
                )
                assignments[fid] = {
                    "target_wall": wall,
                    "alignment": align,
                    "offset_from_wall": 0.05,
                    "facing": "",
                }
                wall_usage[wall] += fw
                dining_table_wall = wall
                logger.info(f"WallAssigner: {fid} ({ft}) → {wall} wall (center, dining_table)")
                continue

            # Default: small/misc items — prefer non-door walls but allow door wall
            # if all other walls are too crowded, spatial_resolver will place beside door
            exclude_default = door_walls.copy()
            # Also exclude walls already occupied by key furniture (bed, sofa)
            if bed_assigned_wall:
                exclude_default.add(bed_assigned_wall)
            if sofa_assigned_wall:
                exclude_default.add(sofa_assigned_wall)
            crowded_non_door = {
                w for w in (_ALL_WALLS - door_walls)
                if wall_usage.get(w, 0.0) > _wall_length(w, room_w, room_d) * 0.6
            }
            if exclude_default >= _ALL_WALLS or crowded_non_door >= (_ALL_WALLS - door_walls):
                # All preferred walls taken — allow door wall as last resort
                exclude_default = door_walls.copy()
            llm_choice = llm_walls.get(fid)
            if llm_choice and llm_choice not in exclude_default and llm_choice in _ALL_WALLS:
                wall = llm_choice
                logger.info(f"WallAssigner: {fid} using LLM wall={wall!r}")
            else:
                if llm_choice and llm_choice in exclude_default:
                    logger.info(
                        f"WallAssigner: {fid} LLM wall={llm_choice!r} conflicts with bed/door → picking alternate"
                    )
                wall = self._pick_wall(
                    exclude=exclude_default,
                    prefer_side=False,
                    room_w=room_w,
                    room_d=room_d,
                    wall_usage=wall_usage,
                    item_width=fw,
                )
            align = (
                self._safe_alignment_for_door_wall(
                    wall, fw, room_w, room_d, room_spec.get("doors", [])
                )
                if wall in door_walls
                else self._pick_alignment(wall, wall_usage, fw, room_w, room_d)
            )
            assignments[fid] = {
                "target_wall": wall,
                "alignment": align,
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

    @staticmethod
    def _safe_alignment_for_door_wall(
        wall: str,
        item_width: float,
        room_w: float,
        room_d: float,
        doors: list[dict[str, Any]],
    ) -> str:
        """Return alignment that keeps item away from door clearance zone.

        Picks the side of the wall (left or right) that has the most space
        away from any door on that wall. Used to prevent furniture from
        landing in the walking path in front of the door.
        """
        wall_len = _wall_length(wall, room_w, room_d)
        best_align = "left"
        best_space = -1.0
        for door in doors:
            if str(door.get("wall", "")).lower() != wall:
                continue
            door_off = float(door.get("offset", 0.0))
            door_w = float(door.get("width", 0.9))
            _SIDE_CLEAR = 0.6  # match spatial_resolver _SIDE_PAD + a bit
            # Space on each side OUTSIDE the door+padding zone
            left_clear = door_off - _SIDE_CLEAR
            right_clear = wall_len - (door_off + door_w + _SIDE_CLEAR)
            if right_clear >= left_clear:
                align = "right"
                space = right_clear
            else:
                align = "left"
                space = left_clear
            if space > best_space:
                best_space = space
                best_align = align
        return best_align
