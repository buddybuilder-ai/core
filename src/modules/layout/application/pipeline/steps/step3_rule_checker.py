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
from typing import Any, AsyncGenerator

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

    async def execute(
        self, state: PipelineState
    ) -> AsyncGenerator[SSEEvent, None]:
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

        # --- Universal Standards ---
        yield self._emit_progress("Checking universal standards...", 0.2)
        universal_conflicts = self._check_universal_standards(items, room, spec)

        # --- Feng Shui Principles ---
        yield self._emit_progress("Checking feng shui principles...", 0.6)
        feng_shui_conflicts = self._check_feng_shui(items, room, spec)

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

        # Collect all conflicts
        all_conflicts = universal_conflicts + feng_shui_conflicts
        state.conflicts.extend(all_conflicts)

        # Emit each conflict
        for conflict in all_conflicts:
            yield SSEEvent(
                event_type=SSEEventType.CONFLICT_FOUND,
                data=conflict.to_dict(),
            )

        yield self._emit_completed({
            "universal_issues": len(universal_conflicts),
            "feng_shui_issues": len(feng_shui_conflicts),
            "total_conflicts": len(all_conflicts),
            "feng_shui_score": state.feng_shui_score,
            "total_score": scoring_result.score.total,
            "grade": scoring_result.score.grade,
        })

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
            for item_b, box_b in zip(items[i + 1:], boxes[i + 1:]):
                if box_a.intersects(box_b):
                    conflicts.append(Conflict(
                        conflict_type=ConflictType.OVERLAP,
                        severity=ConflictSeverity.CRITICAL,
                        description=f"{item_a['name']} overlaps with {item_b['name']}",
                        items_involved=[item_a["id"], item_b["id"]],
                        suggestion=f"Shift {item_a['name']} or {item_b['name']} apart",
                    ))
                else:
                    gap = box_a.distance_to(box_b)
                    if 0 < gap < MIN_CLEARANCE:
                        conflicts.append(Conflict(
                            conflict_type=ConflictType.CLEARANCE_VIOLATION,
                            severity=ConflictSeverity.WARNING,
                            description=(
                                f"{item_a['name']} and {item_b['name']} "
                                f"too close ({gap:.2f}m < {MIN_CLEARANCE}m)"
                            ),
                            items_involved=[item_a["id"], item_b["id"]],
                            suggestion="Increase spacing between items",
                        ))

        # Check out of bounds
        for item, box in zip(items, boxes):
            if (
                box.min_x < -0.01
                or box.min_z < -0.01
                or box.max_x > room.width + 0.01
                or box.max_z > room.depth + 0.01
            ):
                conflicts.append(Conflict(
                    conflict_type=ConflictType.OUT_OF_BOUNDS,
                    severity=ConflictSeverity.CRITICAL,
                    description=f"{item['name']} extends outside room boundaries",
                    items_involved=[item["id"]],
                    suggestion="Move item within room bounds",
                ))

        # Check door blocking
        for door in spec.get("doors", []):
            door_center = self._get_door_center(door, room)
            door_zone = AABB.from_center_and_size(
                door_center[0], door_center[1],
                DOOR_CLEARANCE * 2, DOOR_CLEARANCE * 2,
            )
            for item, box in zip(items, boxes):
                if box.intersects(door_zone):
                    conflicts.append(Conflict(
                        conflict_type=ConflictType.DOOR_BLOCKED,
                        severity=ConflictSeverity.CRITICAL,
                        description=f"{item['name']} blocks door on {door.get('wall', 'wall')} wall",
                        items_involved=[item["id"]],
                        suggestion=f"Move {item['name']} away from door",
                    ))

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

        for item in items:
            category = item.get("category", "")
            if category not in key_categories:
                continue

            pos_x = item.get("pos_x", 0)
            pos_z = item.get("pos_z", 0)
            dims = item.get("dimensions", {})
            w = dims.get("width", 1)
            d = dims.get("depth", 1)
            center_x = pos_x + w / 2
            center_z = pos_z + d / 2

            # Check back to door
            rotation = item.get("rotation", 0)
            if self._has_back_to_door(center_x, center_z, rotation, door_x, door_z):
                conflicts.append(Conflict(
                    conflict_type=ConflictType.BACK_TO_DOOR,
                    severity=ConflictSeverity.WARNING,
                    description=f"{item['name']} has its back facing the door",
                    items_involved=[item["id"]],
                    suggestion=f"Rotate {item['name']} to face the door",
                ))

            # Check sha chi alignment (direct line with door)
            if self._is_aligned_with_door(center_x, center_z, w, d, door_x, door_z):
                conflicts.append(Conflict(
                    conflict_type=ConflictType.SHA_CHI_ALIGNMENT,
                    severity=ConflictSeverity.INFO,
                    description=f"{item['name']} is in direct line with the door (sha chi)",
                    items_involved=[item["id"]],
                    suggestion=f"Shift {item['name']} off the door axis",
                ))

        return conflicts

    # --- Helpers ---

    def _build_boxes(self, items: list[dict]) -> list[AABB]:
        boxes = []
        for item in items:
            dims = item.get("dimensions", {})
            rotation = item.get("rotation", 0)
            w = dims.get("width", 1)
            d = dims.get("depth", 1)
            if rotation in (90, 270):
                w, d = d, w
            boxes.append(AABB.from_position_and_size(
                item.get("pos_x", 0),
                item.get("pos_z", 0),
                w, d,
            ))
        return boxes

    def _get_door_center(self, door: dict, room: Room) -> tuple[float, float]:
        wall = door.get("wall", "south")
        offset = door.get("offset", 1.0)
        width = door.get("width", 0.9)
        center = offset + width / 2
        if wall == "north":
            return center, 0
        elif wall == "south":
            return center, room.depth
        elif wall == "west":
            return 0, center
        else:
            return room.width, center

    def _get_primary_door_pos(self, room: Room) -> tuple[float, float]:
        if room.doors:
            d = room.doors[0]
            return self._get_door_center(
                {"wall": d.wall, "offset": d.offset, "width": d.width}, room
            )
        return room.width / 2, room.depth

    def _has_back_to_door(
        self, cx: float, cz: float, rotation: int, dx: float, dz: float
    ) -> bool:
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

    def _items_to_placed(self, items: list[dict]) -> list[PlacedFurniture]:
        result = []
        for item in items:
            dims = item.get("dimensions", {})
            result.append(PlacedFurniture(
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
            ))
        return result
