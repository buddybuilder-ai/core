"""Step 3: Rule Checker (Dual-rule).

Checks layout against:
1. Universal Standards — min clearance, overlap, door/window blocking, walkway
2. Feng Shui Principles — command position, element balance, chi flow, sha chi

Currently uses code-based rules (pipeline stub).
Interface is RAG-ready for future knowledge retrieval.
"""

from __future__ import annotations

import logging
import math
from collections.abc import AsyncGenerator
from dataclasses import replace
from typing import Any

from src.modules.layout.application.dtos import PlacedFurniture
from src.modules.layout.application.pipeline.models import (
    Conflict,
    ConflictSeverity,
    ConflictType,
    PipelineConfig,
    PipelineState,
    PipelineStep,
    SSEEvent,
    SSEEventType,
)
from src.modules.layout.application.pipeline.steps.base import BaseStep
from src.modules.layout.application.services import FengShuiScorer
from src.modules.layout.domain.entities import Room
from src.modules.layout.infrastructure.geometry import AABB

logger = logging.getLogger(__name__)

# Minimum clearance between furniture (meters)
MIN_CLEARANCE = 0.6
# Minimum door clearance zone (meters)
DOOR_CLEARANCE = 0.9
# Minimum walkway width (meters)
MIN_WALKWAY = 0.7


class RuleCheckerStep(BaseStep):
    """Step 3: Check layout against universal standards and feng shui."""

    step = PipelineStep.RULE_CHECKER

    def __init__(self, config: PipelineConfig) -> None:
        super().__init__(config)
        self._scorer = FengShuiScorer()

    async def execute(self, state: PipelineState) -> AsyncGenerator[SSEEvent, None]:
        yield self._emit_started()

        items = state.layout_items
        spec = state.room_spec
        room: Room | None = spec.get("_room")

        if not items:
            raise ValueError("No layout items — run Step 2 first")
        if not room:
            raise ValueError("No room model — run Step 1 first")

        # Reset conflicts for this check pass
        # Keep previously resolved ones for history
        state.conflicts = [c for c in state.conflicts if c.resolved]

        logger.info(f"🔍 STEP 3: Checking {len(items)} furniture items against rules")

        # --- Universal Standards ---
        yield self._emit_progress("Checking universal standards...", 0.2)
        logger.info("   Checking universal standards (overlap, clearance, doors)...")
        universal_conflicts = self._check_universal_standards(items, room, spec)
        logger.info(f"   ✓ Universal check: {len(universal_conflicts)} issues found")
        for conflict in universal_conflicts[:3]:
            logger.info(f"      - [{conflict.severity.value.upper()}] {conflict.description}")
        if len(universal_conflicts) > 3:
            logger.info(f"      ... and {len(universal_conflicts) - 3} more")

        # --- Feng Shui Principles ---
        yield self._emit_progress("Checking feng shui principles...", 0.6)
        logger.info("   Checking feng shui principles (command pos, chi flow)...")
        feng_shui_conflicts = self._check_feng_shui(items, room, spec)
        logger.info(f"   ✓ Feng shui check: {len(feng_shui_conflicts)} issues found")
        for conflict in feng_shui_conflicts:
            logger.info(f"      - [{conflict.severity.value.upper()}] {conflict.description}")

        # --- Score layout ---
        yield self._emit_progress("Scoring layout...", 0.8)
        placed_furniture = self._items_to_placed(items)
        spatial = spec.get("_spatial")
        scoring_result = self._scorer.score_layout(room, placed_furniture, spatial)
        state.feng_shui_score = {
            "command_position": scoring_result.score.command_position,
            "five_elements_balance": scoring_result.score.five_elements,
            "chi_flow": scoring_result.score.chi_flow,
            "sha_chi_avoidance": scoring_result.score.sha_chi_avoidance,
        }

        # Enrich conflict suggestions with RAG rule descriptions (no-op if empty)
        rule_descs = state.rag_context.get("rule_descriptions", {})
        all_conflicts = self._enrich_with_rag(universal_conflicts + feng_shui_conflicts, rule_descs)
        state.conflicts.extend(all_conflicts)

        # Emit each conflict
        for conflict in all_conflicts:
            yield SSEEvent(
                event_type=SSEEventType.CONFLICT_FOUND,
                data=conflict.to_dict(),
            )

        yield self._emit_completed(
            {
                "universal_issues": len(universal_conflicts),
                "feng_shui_issues": len(feng_shui_conflicts),
                "total_conflicts": len(all_conflicts),
                "feng_shui_score": state.feng_shui_score,
                "total_score": scoring_result.score.total,
                "grade": scoring_result.score.grade,
            }
        )

    # --- RAG enrichment ---

    # Maps ConflictType value → rule_id in the knowledge base
    _CONFLICT_RULE_MAP: dict[str, str] = {
        "back_to_door": "cmd_001",
        "bad_command_position": "cmd_001",
        "sha_chi_alignment": "sha_001",
        "element_imbalance": "elem_001",
        "blocked_chi_flow": "chi_001",
    }

    @classmethod
    def _enrich_with_rag(
        cls,
        conflicts: list[Conflict],
        rule_descriptions: dict[str, str],
    ) -> list[Conflict]:
        """Append knowledge-base rule text to conflict suggestions where available.

        Args:
            conflicts: Detected conflicts.
            rule_descriptions: Mapping of rule_id → description from RAG context.

        Returns:
            Same conflicts with enriched suggestion strings.
        """
        if not rule_descriptions:
            return conflicts
        enriched: list[Conflict] = []
        for c in conflicts:
            rule_id = cls._CONFLICT_RULE_MAP.get(c.conflict_type.value)
            if rule_id and rule_id in rule_descriptions:
                enriched.append(
                    replace(
                        c,
                        suggestion=(f"{c.suggestion}  (Rule: {rule_descriptions[rule_id]})"),
                    )
                )
            else:
                enriched.append(c)
        return enriched

    def _check_universal_standards(
        self,
        items: list[dict[str, Any]],
        room: Room,
        spec: dict[str, Any],
    ) -> list[Conflict]:
        conflicts: list[Conflict] = []
        boxes = self._build_boxes(items)

        # Check overlaps + clearance between all pairs
        for i, (item_a, box_a) in enumerate(zip(items, boxes)):
            for item_b, box_b in zip(items[i + 1 :], boxes[i + 1 :]):
                if box_a.intersects(box_b):
                    conflicts.append(
                        Conflict(
                            conflict_type=ConflictType.OVERLAP,
                            severity=ConflictSeverity.CRITICAL,
                            description=f"{item_a['name']} overlaps with {item_b['name']}",
                            items_involved=[item_a["id"], item_b["id"]],
                            suggestion=f"Shift {item_a['name']} or {item_b['name']} apart",
                        )
                    )
                else:
                    gap = box_a.distance_to(box_b)
                    if 0 < gap < MIN_CLEARANCE:
                        conflicts.append(
                            Conflict(
                                conflict_type=ConflictType.CLEARANCE_VIOLATION,
                                severity=ConflictSeverity.WARNING,
                                description=(
                                    f"{item_a['name']} and {item_b['name']} "
                                    f"too close ({gap:.2f}m < {MIN_CLEARANCE}m)"
                                ),
                                items_involved=[item_a["id"], item_b["id"]],
                                suggestion="Increase spacing between items",
                            )
                        )

        # Check out of bounds (box is centre-based, room limits are ±half)
        half_w = room.width / 2
        half_d = room.depth / 2
        for item, box in zip(items, boxes):
            if (
                box.min_x < -half_w - 0.01
                or box.min_z < -half_d - 0.01
                or box.max_x > half_w + 0.01
                or box.max_z > half_d + 0.01
            ):
                conflicts.append(
                    Conflict(
                        conflict_type=ConflictType.OUT_OF_BOUNDS,
                        severity=ConflictSeverity.CRITICAL,
                        description=f"{item['name']} extends outside room boundaries",
                        items_involved=[item["id"]],
                        suggestion="Move item within room bounds",
                    )
                )

        # Check door blocking
        for door in spec.get("doors", []):
            door_center = self._get_door_center(door, room)
            door_zone = AABB.from_center_and_size(
                door_center[0],
                door_center[1],
                DOOR_CLEARANCE * 2,
                DOOR_CLEARANCE * 2,
            )
            for item, box in zip(items, boxes):
                if box.intersects(door_zone):
                    conflicts.append(
                        Conflict(
                            conflict_type=ConflictType.DOOR_BLOCKED,
                            severity=ConflictSeverity.CRITICAL,
                            description=f"{item['name']} blocks door on {door.get('wall', 'wall')} wall",
                            items_involved=[item["id"]],
                            suggestion=f"Move {item['name']} away from door",
                        )
                    )

        return conflicts

    def _check_feng_shui(
        self,
        items: list[dict[str, Any]],
        room: Room,
        spec: dict[str, Any],
    ) -> list[Conflict]:
        conflicts: list[Conflict] = []

        door_x, door_z = self._get_primary_door_pos(room)
        key_categories = {"bed", "desk", "sofa"}

        # Build window centre positions (room-centre coords)
        window_positions = [
            self._get_feature_center(w, room)
            for w in (spec.get("windows") or [])
        ]

        # Index items by category for relationship checks
        large_types = {"wardrobe", "bookshelf", "dresser", "compact_wardrobe"}
        large_items = [i for i in items if i.get("category") in large_types]
        screen_types = {"tv_stand", "tv", "monitor", "mirror"}
        screen_items = [i for i in items if i.get("category") in screen_types]

        for item in items:
            category = item.get("category", "")
            center_x = item.get("pos_x", 0.0)
            center_z = item.get("pos_z", 0.0)
            rotation = item.get("rotation", 0)
            fw, fd = self._footprint(item.get("dimensions", {}), rotation)

            if category == "bed":
                # Rule bed_001 — bed aligned with door
                if self._is_aligned_with_door(center_x, center_z, fw, fd, door_x, door_z):
                    conflicts.append(Conflict(
                        conflict_type=ConflictType.SHA_CHI_ALIGNMENT,
                        severity=ConflictSeverity.WARNING,
                        description=f"{item['name']} is directly aligned with the door (coffin position)",
                        items_involved=[item["id"]],
                        suggestion=f"Shift {item['name']} off the door axis to avoid sha chi",
                    ))

                # Rule bed_002 — bed aligned with window
                for wx, wz in window_positions:
                    if self._is_aligned_with_door(center_x, center_z, fw, fd, wx, wz):
                        conflicts.append(Conflict(
                            conflict_type=ConflictType.SHA_CHI_ALIGNMENT,
                            severity=ConflictSeverity.WARNING,
                            description=f"{item['name']} is directly aligned with a window",
                            items_involved=[item["id"]],
                            suggestion=f"Shift {item['name']} off the window axis",
                        ))
                        break

                # Rule bed_005 — bed not against any wall (floating in center)
                half_w, half_d = room.width / 2, room.depth / 2
                wall_tol = 0.3
                near_wall = (
                    abs(center_x - half_w) < (fw / 2 + wall_tol)
                    or abs(center_x + half_w) < (fw / 2 + wall_tol)
                    or abs(center_z - half_d) < (fd / 2 + wall_tol)
                    or abs(center_z + half_d) < (fd / 2 + wall_tol)
                )
                if not near_wall:
                    conflicts.append(Conflict(
                        conflict_type=ConflictType.BAD_COMMAND_POSITION,
                        severity=ConflictSeverity.WARNING,
                        description=f"{item['name']} is floating in the center of the room with no wall support",
                        items_involved=[item["id"]],
                        suggestion=f"Move {item['name']} against a solid wall for support energy",
                    ))

                # Rule bed_003 — TV or mirror directly facing the bed
                bed_box = AABB.from_center_and_size(center_x, center_z, fw, fd)
                for screen in screen_items:
                    sx, sz = screen.get("pos_x", 0.0), screen.get("pos_z", 0.0)
                    srot = screen.get("rotation", 0)
                    sfw, sfd = self._footprint(screen.get("dimensions", {}), srot)
                    # "facing bed" = screen centre is roughly in front of bed (within bed width on x, or depth on z)
                    if abs(sx - center_x) < (fw / 2 + sfw / 2 + 0.3) and abs(sz - center_z) < (fd / 2 + sfd / 2 + 0.3):
                        conflicts.append(Conflict(
                            conflict_type=ConflictType.SHA_CHI_ALIGNMENT,
                            severity=ConflictSeverity.WARNING,
                            description=f"{screen['name']} is directly facing the bed — mirrors/TVs disturb sleep",
                            items_involved=[item["id"], screen["id"]],
                            suggestion=f"Move {screen['name']} to a side wall or angle it away from the bed",
                        ))

                # Rule bed_004 — AC directly above / in airflow line of bed
                ac_items = [i for i in items if i.get("category") in ("air_conditioner", "ac")]
                for ac in ac_items:
                    ax, az = ac.get("pos_x", 0.0), ac.get("pos_z", 0.0)
                    arot = ac.get("rotation", 0)
                    afw, afd = self._footprint(ac.get("dimensions", {}), arot)
                    # AC on same x-strip or z-strip as bed → airflow blows on sleeper
                    if abs(ax - center_x) < (fw / 2 + afw / 2 + 0.2) or abs(az - center_z) < (fd / 2 + afd / 2 + 0.2):
                        conflicts.append(Conflict(
                            conflict_type=ConflictType.SHA_CHI_ALIGNMENT,
                            severity=ConflictSeverity.WARNING,
                            description=f"{ac['name']} blows cold air directly onto the bed — harmful to health",
                            items_involved=[item["id"], ac["id"]],
                            suggestion=f"Move bed out of the direct airflow of {ac['name']}",
                        ))

                # Rule bed_011 — screen/monitor at the headboard end of the bed
                back_z_offset_head = math.cos(math.radians(rotation)) * (fd / 2)
                head_z = center_z + back_z_offset_head
                for screen in screen_items:
                    sx, sz = screen.get("pos_x", 0.0), screen.get("pos_z", 0.0)
                    srot = screen.get("rotation", 0)
                    sfw, sfd = self._footprint(screen.get("dimensions", {}), srot)
                    if (
                        abs(sx - center_x) < (fw / 2 + sfw / 2 + 0.1)
                        and abs(sz - head_z) < (sfd / 2 + fd / 4 + 0.2)
                    ):
                        conflicts.append(Conflict(
                            conflict_type=ConflictType.SHA_CHI_ALIGNMENT,
                            severity=ConflictSeverity.WARNING,
                            description=f"{screen['name']} is at the headboard of {item['name']} — EMF disturbs sleep",
                            items_involved=[item["id"], screen["id"]],
                            suggestion=f"Move {screen['name']} to a side wall away from the head of the bed",
                        ))

                # Rule bed_007 — large furniture on same wall as bed headboard
                # Determine which wall the bed headboard is on (wall the bed is pushed against)
                half_w, half_d = room.width / 2, room.depth / 2
                wall_tol = 0.4
                bed_headboard_wall: str | None = None
                if abs(center_z + half_d) < (fd / 2 + wall_tol):
                    bed_headboard_wall = "north"  # bed pushed against north wall (z ≈ -half_d)
                elif abs(center_z - half_d) < (fd / 2 + wall_tol):
                    bed_headboard_wall = "south"
                elif abs(center_x + half_w) < (fw / 2 + wall_tol):
                    bed_headboard_wall = "west"
                elif abs(center_x - half_w) < (fw / 2 + wall_tol):
                    bed_headboard_wall = "east"

                if bed_headboard_wall:
                    for large in large_items:
                        lx = large.get("pos_x", 0.0)
                        lz = large.get("pos_z", 0.0)
                        lrot = large.get("rotation", 0)
                        lfw, lfd = self._footprint(large.get("dimensions", {}), lrot)
                        # Check if large item is on same wall as bed headboard
                        large_on_same_wall = (
                            (bed_headboard_wall == "north" and abs(lz + half_d) < (lfd / 2 + wall_tol))
                            or (bed_headboard_wall == "south" and abs(lz - half_d) < (lfd / 2 + wall_tol))
                            or (bed_headboard_wall == "west" and abs(lx + half_w) < (lfw / 2 + wall_tol))
                            or (bed_headboard_wall == "east" and abs(lx - half_w) < (lfw / 2 + wall_tol))
                        )
                        if large_on_same_wall:
                            conflicts.append(Conflict(
                                conflict_type=ConflictType.SHA_CHI_ALIGNMENT,
                                severity=ConflictSeverity.WARNING,
                                description=(
                                    f"{large['name']} is on the same wall as the bed headboard ({bed_headboard_wall}) "
                                    f"— heavy furniture at the head creates oppressive pressure"
                                ),
                                items_involved=[item["id"], large["id"]],
                                suggestion=f"Move {large['name']} to a side wall away from the bed headboard",
                            ))

                # Rule bed_008 — no clearance on any side
                has_clearance = True
                for other in items:
                    if other["id"] == item["id"]:
                        continue
                    ox, oz = other.get("pos_x", 0.0), other.get("pos_z", 0.0)
                    orot = other.get("rotation", 0)
                    ofw, ofd = self._footprint(other.get("dimensions", {}), orot)
                    other_box = AABB.from_center_and_size(ox, oz, ofw, ofd)
                    if 0 < bed_box.distance_to(other_box) < 0.4:
                        has_clearance = False
                        break
                if not has_clearance:
                    conflicts.append(Conflict(
                        conflict_type=ConflictType.CLEARANCE_VIOLATION,
                        severity=ConflictSeverity.INFO,
                        description=f"{item['name']} has insufficient clearance on all sides",
                        items_involved=[item["id"]],
                        suggestion=f"Leave at least 60 cm clearance on one side of {item['name']}",
                    ))

            elif category in key_categories:
                # Check back to door (for desk, sofa)
                if self._has_back_to_door(center_x, center_z, rotation, door_x, door_z):
                    conflicts.append(Conflict(
                        conflict_type=ConflictType.BACK_TO_DOOR,
                        severity=ConflictSeverity.WARNING,
                        description=f"{item['name']} has its back facing the door",
                        items_involved=[item["id"]],
                        suggestion=f"Rotate {item['name']} to face the door",
                    ))

                # Rule bed_009 — desk facing window directly
                if category == "desk":
                    for wx, wz in window_positions:
                        if self._is_aligned_with_door(center_x, center_z, fw, fd, wx, wz):
                            conflicts.append(Conflict(
                                conflict_type=ConflictType.SHA_CHI_ALIGNMENT,
                                severity=ConflictSeverity.INFO,
                                description=f"{item['name']} faces directly into a window (glare, scattered chi)",
                                items_involved=[item["id"]],
                                suggestion=f"Angle {item['name']} so natural light comes from the side",
                            ))
                            break

        # Rule bed_006 — door directly opposite window
        for door in (spec.get("doors") or []):
            dx, dz = self._get_door_center(door, room)
            for wx, wz in window_positions:
                if abs(dx - wx) < 0.5 and abs(dz - wz) < room.depth * 0.6:
                    conflicts.append(Conflict(
                        conflict_type=ConflictType.BLOCKED_CHI_FLOW,
                        severity=ConflictSeverity.INFO,
                        description="Door and window are directly opposite — chi rushes through without circulating",
                        items_involved=[],
                        suggestion="Place a plant or furniture between door and window to slow chi flow",
                    ))

        return conflicts

    def _get_feature_center(self, feature: dict[str, Any], room: Room) -> tuple[float, float]:
        """Return centre of a door or window in room-centre coordinates."""
        wall = feature.get("wall", "south")
        offset = feature.get("offset", 1.0)
        width = feature.get("width", 1.0)
        half_w = room.width / 2
        half_d = room.depth / 2
        mid = offset + width / 2
        if wall == "north":
            return mid - half_w, -half_d
        if wall == "south":
            return mid - half_w, half_d
        if wall == "west":
            return -half_w, mid - half_d
        return half_w, mid - half_d

    # --- Helpers ---

    @staticmethod
    def _footprint(dims: dict[str, Any], rotation: int) -> tuple[float, float]:
        """Return (fw, fd) footprint extents along X and Z in room space.

        _physical_to_dict stores pre-rotation dimensions (for Three.js BoxGeometry)
        and swaps width/depth back for 90/270° so rendering is correct. We swap
        again here to recover the actual room footprint extents.
        """
        w = dims.get("width", 1.0)
        d = dims.get("depth", 1.0)
        if rotation % 360 in (90, 270):
            return d, w
        return w, d

    def _build_boxes(self, items: list[dict[str, Any]]) -> list[AABB]:
        """Build centre-based AABBs. pos_x/pos_z are furniture centres."""
        boxes = []
        for item in items:
            fw, fd = self._footprint(item.get("dimensions", {}), item.get("rotation", 0))
            boxes.append(
                AABB.from_center_and_size(
                    item.get("pos_x", 0.0),
                    item.get("pos_z", 0.0),
                    fw,
                    fd,
                )
            )
        return boxes

    def _get_door_center(self, door: dict[str, Any], room: Room) -> tuple[float, float]:
        """Return door centre in room-centre coordinate system."""
        wall = door.get("wall", "south")
        offset = door.get("offset", 1.0)
        width = door.get("width", 0.9)
        # offset is from the SW corner along the wall edge
        # convert to room-centre coords
        half_w = room.width / 2
        half_d = room.depth / 2
        door_mid = offset + width / 2
        if wall == "north":
            return door_mid - half_w, -half_d
        if wall == "south":
            return door_mid - half_w, half_d
        if wall == "west":
            return -half_w, door_mid - half_d
        # east
        return half_w, door_mid - half_d

    def _get_primary_door_pos(self, room: Room) -> tuple[float, float]:
        if room.doors:
            d = room.doors[0]
            return self._get_door_center(
                {"wall": d.wall, "offset": d.offset, "width": d.width}, room
            )
        return 0.0, room.depth / 2

    def _has_back_to_door(self, cx: float, cz: float, rotation: int, dx: float, dz: float) -> bool:
        door_angle = math.degrees(math.atan2(dz - cz, dx - cx))
        door_angle = (door_angle + 360) % 360
        back_dir = (rotation + 180) % 360
        diff = abs(door_angle - back_dir)
        diff = min(diff, 360 - diff)
        return diff < 60

    def _is_aligned_with_door(
        self, cx: float, cz: float, w: float, d: float, dx: float, dz: float
    ) -> bool:
        return abs(cx - dx) < w * 0.5 or abs(cz - dz) < d * 0.5

    def _items_to_placed(self, items: list[dict[str, Any]]) -> list[PlacedFurniture]:
        result = []
        for item in items:
            dims = item.get("dimensions", {})
            result.append(
                PlacedFurniture(
                    id=item.get("id", ""),
                    furniture_id=item.get("furniture_id", item.get("id", "")),
                    name=item.get("name", ""),
                    category=item.get("category", ""),
                    pos_x=item.get("pos_x", 0),
                    pos_z=item.get("pos_z", 0),
                    width=dims.get("width", 1),
                    depth=dims.get("depth", 1),
                    height=dims.get("height", 1),
                    rotation=item.get("rotation", 0),
                    is_essential=item.get("is_essential", False),
                )
            )
        return result
