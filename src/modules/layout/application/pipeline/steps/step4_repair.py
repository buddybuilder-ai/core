"""Step 4: Repair (Auto-fix).

Applies local search fixes to resolve conflicts:
- Shift: move furniture to nearby valid position
- Rotate: try different rotation angles
- Swap: swap positions of two conflicting items
- Remove: last resort — remove non-essential item

Loops back to Step 3 (Rule Checker) if conflicts remain,
up to max_repair_loops iterations.
"""

from __future__ import annotations

import logging
from typing import Any, AsyncGenerator

from src.modules.layout.application.pipeline.models import (
    Conflict,
    ConflictSeverity,
    ConflictType,
    PipelineConfig,
    PipelineState,
    PipelineStep,
    RepairAction,
    RepairActionType,
    SSEEvent,
    SSEEventType,
)
from src.modules.layout.application.pipeline.steps.base import BaseStep
from src.modules.layout.domain.entities import Room
from src.modules.layout.infrastructure.geometry import AABB

logger = logging.getLogger(__name__)

# How far to try shifting (meters)
SHIFT_INCREMENTS = [0.3, 0.5, 0.8, 1.0]
SHIFT_DIRECTIONS = [
    (1, 0), (-1, 0), (0, 1), (0, -1),
    (1, 1), (-1, 1), (1, -1), (-1, -1),
]


class RepairStep(BaseStep):
    """Step 4: Auto-fix conflicts via local search."""

    step = PipelineStep.REPAIR

    async def execute(
        self, state: PipelineState
    ) -> AsyncGenerator[SSEEvent, None]:
        yield self._emit_started()

        spec = state.room_spec
        room: Room | None = spec.get("_room")
        if not room:
            raise ValueError("No room model — run Step 1 first")

        unresolved = state.unresolved_conflicts
        if not unresolved:
            logger.info(f"🔧 STEP 4: No conflicts to repair - skipping")
            yield self._emit_progress("No conflicts to repair", 1.0)
            yield self._emit_completed({"repairs_applied": 0})
            return

        total = len(unresolved)
        repaired = 0

        logger.info(f"🔧 STEP 4: Repairing {total} conflicts")
        logger.info(f"   Strategy: Shift → Rotate → Swap → Remove (last resort)")

        for i, conflict in enumerate(unresolved):
            progress = (i + 1) / total
            yield self._emit_progress(
                f"Repairing conflict {i + 1}/{total}: {conflict.description}",
                progress * 0.9,
            )

            logger.info(f"   [{i+1}/{total}] {conflict.conflict_type.value}: {conflict.description[:60]}...")
            action = self._try_repair(conflict, state.layout_items, room)
            if action and action.success:
                conflict.resolved = True
                state.repair_actions.append(action)
                repaired += 1
                logger.info(f"      ✓ Fixed with {action.action_type.value}: {action.description}")
            else:
                logger.info(f"      ✗ Could not fix automatically")

                yield SSEEvent(
                    event_type=SSEEventType.REPAIR_APPLIED,
                    data=action.to_dict(),
                )

        # Emit updated layout after repairs
        if repaired > 0:
            yield SSEEvent(
                event_type=SSEEventType.LAYOUT_UPDATED,
                data={"items": state.layout_items, "step": self.step.value},
            )

        yield self._emit_completed({
            "repairs_applied": repaired,
            "remaining_conflicts": len(state.unresolved_conflicts),
        })

    def _try_repair(
        self,
        conflict: Conflict,
        items: list[dict[str, Any]],
        room: Room,
    ) -> RepairAction | None:
        """Try to repair a single conflict."""
        if conflict.conflict_type in (
            ConflictType.OVERLAP,
            ConflictType.CLEARANCE_VIOLATION,
            ConflictType.DOOR_BLOCKED,
            ConflictType.WINDOW_BLOCKED,
            ConflictType.OUT_OF_BOUNDS,
        ):
            return self._try_shift(conflict, items, room)

        if conflict.conflict_type in (
            ConflictType.BACK_TO_DOOR,
            ConflictType.SHA_CHI_ALIGNMENT,
        ):
            result = self._try_rotate(conflict, items, room)
            if result and result.success:
                return result
            return self._try_shift(conflict, items, room)

        return None

    def _try_shift(
        self,
        conflict: Conflict,
        items: list[dict[str, Any]],
        room: Room,
    ) -> RepairAction | None:
        """Try shifting the first involved item to resolve conflict."""
        if not conflict.items_involved:
            return None

        target_id = conflict.items_involved[0]
        target = self._find_item(target_id, items)
        if not target:
            return None

        original_x = target.get("pos_x", 0)
        original_z = target.get("pos_z", 0)
        dims = target.get("dimensions", {})
        rotation = target.get("rotation", 0)
        w = dims.get("width", 1)
        d = dims.get("depth", 1)
        if rotation in (90, 270):
            w, d = d, w

        for dist in SHIFT_INCREMENTS:
            for dx, dz in SHIFT_DIRECTIONS:
                new_x = original_x + dx * dist
                new_z = original_z + dz * dist

                # Bounds check
                if new_x < 0 or new_z < 0:
                    continue
                if new_x + w > room.width or new_z + d > room.depth:
                    continue

                # Collision check against other items
                new_box = AABB.from_position_and_size(new_x, new_z, w, d)
                has_collision = False
                for other in items:
                    if other.get("id") == target_id:
                        continue
                    o_dims = other.get("dimensions", {})
                    o_rot = other.get("rotation", 0)
                    ow = o_dims.get("width", 1)
                    od = o_dims.get("depth", 1)
                    if o_rot in (90, 270):
                        ow, od = od, ow
                    other_box = AABB.from_position_and_size(
                        other.get("pos_x", 0), other.get("pos_z", 0), ow, od
                    )
                    if new_box.intersects(other_box):
                        has_collision = True
                        break

                if not has_collision:
                    target["pos_x"] = round(new_x, 3)
                    target["pos_z"] = round(new_z, 3)
                    return RepairAction(
                        action_type=RepairActionType.SHIFT,
                        conflict_id=conflict.id,
                        furniture_id=target_id,
                        description=(
                            f"Shifted {target.get('name', target_id)} "
                            f"from ({original_x:.2f}, {original_z:.2f}) "
                            f"to ({new_x:.2f}, {new_z:.2f})"
                        ),
                        before={"pos_x": original_x, "pos_z": original_z},
                        after={"pos_x": new_x, "pos_z": new_z},
                        success=True,
                    )

        return RepairAction(
            action_type=RepairActionType.SHIFT,
            conflict_id=conflict.id,
            furniture_id=target_id,
            description=f"Could not find valid position for {target.get('name', target_id)}",
            success=False,
        )

    def _try_rotate(
        self,
        conflict: Conflict,
        items: list[dict[str, Any]],
        room: Room,
    ) -> RepairAction | None:
        """Try rotating the involved item."""
        if not conflict.items_involved:
            return None

        target_id = conflict.items_involved[0]
        target = self._find_item(target_id, items)
        if not target:
            return None

        original_rotation = target.get("rotation", 0)
        for new_rotation in [90, 180, 270, 0]:
            if new_rotation == original_rotation:
                continue

            # Check if new rotation fits
            dims = target.get("dimensions", {})
            w = dims.get("width", 1)
            d = dims.get("depth", 1)
            if new_rotation in (90, 270):
                w, d = d, w

            pos_x = target.get("pos_x", 0)
            pos_z = target.get("pos_z", 0)

            if pos_x + w > room.width or pos_z + d > room.depth:
                continue

            new_box = AABB.from_position_and_size(pos_x, pos_z, w, d)
            has_collision = False
            for other in items:
                if other.get("id") == target_id:
                    continue
                o_dims = other.get("dimensions", {})
                o_rot = other.get("rotation", 0)
                ow = o_dims.get("width", 1)
                od = o_dims.get("depth", 1)
                if o_rot in (90, 270):
                    ow, od = od, ow
                other_box = AABB.from_position_and_size(
                    other.get("pos_x", 0), other.get("pos_z", 0), ow, od
                )
                if new_box.intersects(other_box):
                    has_collision = True
                    break

            if not has_collision:
                target["rotation"] = new_rotation
                return RepairAction(
                    action_type=RepairActionType.ROTATE,
                    conflict_id=conflict.id,
                    furniture_id=target_id,
                    description=(
                        f"Rotated {target.get('name', target_id)} "
                        f"from {original_rotation}° to {new_rotation}°"
                    ),
                    before={"rotation": original_rotation},
                    after={"rotation": new_rotation},
                    success=True,
                )

        return None

    def _find_item(
        self, item_id: str, items: list[dict[str, Any]]
    ) -> dict[str, Any] | None:
        for item in items:
            if item.get("id") == item_id:
                return item
        return None
