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
from collections.abc import AsyncGenerator
from typing import Any

from src.modules.layout.application.pipeline.models import (
    Conflict,
    ConflictType,
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
SHIFT_INCREMENTS = [0.3, 0.5, 0.8, 1.0, 1.3, 1.6, 2.0]
# Minimum gap between furniture after shifting (metres)
MIN_SHIFT_CLEARANCE = 0.15
SHIFT_DIRECTIONS = [
    (1, 0),
    (-1, 0),
    (0, 1),
    (0, -1),
    (1, 1),
    (-1, 1),
    (1, -1),
    (-1, -1),
]


class RepairStep(BaseStep):
    """Step 4: Auto-fix conflicts via local search."""

    step = PipelineStep.REPAIR

    async def execute(self, state: PipelineState) -> AsyncGenerator[SSEEvent, None]:
        yield self._emit_started()

        spec = state.room_spec
        room: Room | None = spec.get("_room")
        if not room:
            raise ValueError("No room model — run Step 1 first")

        unresolved = state.unresolved_conflicts
        if not unresolved:
            logger.info("🔧 STEP 4: No conflicts to repair - checking pair alignment")
            reanchored = self._reanchor_pairs(state.layout_items, room)
            if reanchored:
                logger.info(f"🔧 STEP 4: Re-anchored {reanchored} dependent item(s)")
                yield SSEEvent(
                    event_type=SSEEventType.LAYOUT_UPDATED,
                    data={"items": state.layout_items, "step": self.step.value},
                )
            yield self._emit_progress("No conflicts to repair", 1.0)
            yield self._emit_completed({"repairs_applied": 0, "reanchored": reanchored})
            return

        total = len(unresolved)
        repaired = 0

        logger.info(f"🔧 STEP 4: Repairing {total} conflicts")
        logger.info("   Strategy: Shift → Rotate → Swap → Remove (last resort)")

        for i, conflict in enumerate(unresolved):
            progress = (i + 1) / total
            yield self._emit_progress(
                f"Repairing conflict {i + 1}/{total}: {conflict.description}",
                progress * 0.9,
            )

            logger.info(
                f"   [{i + 1}/{total}] {conflict.conflict_type.value}: {conflict.description[:60]}..."
            )
            action = self._try_repair(conflict, state.layout_items, room)
            if action and action.success:
                conflict.resolved = True
                state.repair_actions.append(action)
                repaired += 1
                logger.info(f"      ✓ Fixed with {action.action_type.value}: {action.description}")
            else:
                logger.info("      ✗ Could not fix automatically")

        # Re-center dependent items (chairs) on their anchors (desks/tables)
        # after repair may have shifted them off-center.
        reanchored = self._reanchor_pairs(state.layout_items, room)
        if reanchored:
            logger.info(f"🔧 STEP 4: Re-anchored {reanchored} dependent item(s) to their anchors")

        # Emit updated layout after repairs
        if repaired > 0 or reanchored > 0:
            yield SSEEvent(
                event_type=SSEEventType.LAYOUT_UPDATED,
                data={"items": state.layout_items, "step": self.step.value},
            )

        yield self._emit_completed(
            {
                "repairs_applied": repaired,
                "remaining_conflicts": len(state.unresolved_conflicts),
            }
        )

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

    # ------------------------------------------------------------------
    # Coordinate helpers
    #
    # layout_items use CENTRE-based coordinates (room-centre origin), which
    # is what the frontend expects.  All repair geometry must work in the
    # same system.
    #
    #   half_w = room.width  / 2   (max allowed |pos_x| for a point item)
    #   half_d = room.depth  / 2
    #
    # For a furniture piece of footprint (fw × fd):
    #   valid centre_x range: [-half_w + fw/2,  half_w - fw/2]
    #   valid centre_z range: [-half_d + fd/2,  half_d - fd/2]
    #
    # AABB (which uses corner coords) is built from centre coords by:
    #   AABB.from_center_and_size(cx, cz, fw, fd)
    # ------------------------------------------------------------------

    @staticmethod
    def _footprint_wh(dims: dict[str, Any], rotation: int) -> tuple[float, float]:
        """Return (footprint_x, footprint_z) in room space for a furniture item.

        _physical_to_dict stores pre-rotation dimensions (for Three.js BoxGeometry)
        and swaps width/depth back for 90/270° so rendering is correct. We swap
        again here to recover the actual room footprint extents.
        """
        w = dims.get("width", 1.0)
        d = dims.get("depth", 1.0)
        if rotation % 360 in (90, 270):
            return d, w
        return w, d

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

        original_x = target.get("pos_x", 0.0)
        original_z = target.get("pos_z", 0.0)
        rotation = target.get("rotation", 0)
        fw, fd = self._footprint_wh(target.get("dimensions", {}), rotation)

        half_w = room.width / 2
        half_d = room.depth / 2

        # Pre-build door clearance zones in centre-based coords.
        # spatial_resolver uses 1.5 m clearance + 0.5 m side padding.
        _DOOR_CLEAR = 1.50
        _DOOR_PAD = 0.50
        door_forbidden: list[AABB] = []
        for door in room.doors:
            wall = str(door.wall.value).lower()
            off = float(door.offset)
            dw = float(door.width)
            # Convert corner coords to centre-based coords (subtract half room)
            if wall == "south":
                x0 = max(0.0, off - _DOOR_PAD) - half_w
                x1 = min(room.width, off + dw + _DOOR_PAD) - half_w
                z0 = -half_d
                z1 = _DOOR_CLEAR - half_d
            elif wall == "north":
                x0 = max(0.0, off - _DOOR_PAD) - half_w
                x1 = min(room.width, off + dw + _DOOR_PAD) - half_w
                z0 = half_d - _DOOR_CLEAR
                z1 = half_d
            elif wall == "west":
                x0 = -half_w
                x1 = _DOOR_CLEAR - half_w
                z0 = max(0.0, off - _DOOR_PAD) - half_d
                z1 = min(room.depth, off + dw + _DOOR_PAD) - half_d
            else:  # east
                x0 = half_w - _DOOR_CLEAR
                x1 = half_w
                z0 = max(0.0, off - _DOOR_PAD) - half_d
                z1 = min(room.depth, off + dw + _DOOR_PAD) - half_d
            door_forbidden.append(AABB(min_x=x0, max_x=x1, min_z=z0, max_z=z1))

        for dist in SHIFT_INCREMENTS:
            for dx, dz in SHIFT_DIRECTIONS:
                new_x = original_x + dx * dist
                new_z = original_z + dz * dist

                # Bounds check (centre-based)
                if new_x - fw / 2 < -half_w or new_x + fw / 2 > half_w:
                    continue
                if new_z - fd / 2 < -half_d or new_z + fd / 2 > half_d:
                    continue

                # Collision + clearance check using centre-based AABB
                new_box = AABB.from_center_and_size(new_x, new_z, fw, fd)
                # Expand the candidate box by a small clearance margin so
                # we never place furniture touching/overlapping another item.
                clearance_box = new_box.expanded(MIN_SHIFT_CLEARANCE)
                has_collision = False
                for other in items:
                    if other.get("id") == target_id:
                        continue
                    o_fw, o_fd = self._footprint_wh(
                        other.get("dimensions", {}), other.get("rotation", 0)
                    )
                    other_box = AABB.from_center_and_size(
                        other.get("pos_x", 0.0), other.get("pos_z", 0.0), o_fw, o_fd
                    )
                    if clearance_box.intersects(other_box):
                        has_collision = True
                        break

                # Also reject positions that block door clearance zones
                if not has_collision and any(new_box.intersects(dz) for dz in door_forbidden):
                    has_collision = True

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
        pos_x = target.get("pos_x", 0.0)
        pos_z = target.get("pos_z", 0.0)
        half_w = room.width / 2
        half_d = room.depth / 2

        dims = target.get("dimensions", {})

        for new_rotation in [90, 180, 270, 0]:
            if new_rotation == original_rotation:
                continue

            # _footprint_wh treats stored dims as pre-rotation (Three.js) and
            # swaps for 90/270° to get room-space extents.
            fw, fd = self._footprint_wh(dims, new_rotation)

            # Bounds check (centre-based)
            if pos_x - fw / 2 < -half_w or pos_x + fw / 2 > half_w:
                continue
            if pos_z - fd / 2 < -half_d or pos_z + fd / 2 > half_d:
                continue

            new_box = AABB.from_center_and_size(pos_x, pos_z, fw, fd)
            clearance_box = new_box.expanded(MIN_SHIFT_CLEARANCE)
            has_collision = False
            for other in items:
                if other.get("id") == target_id:
                    continue
                o_fw, o_fd = self._footprint_wh(
                    other.get("dimensions", {}), other.get("rotation", 0)
                )
                other_box = AABB.from_center_and_size(
                    other.get("pos_x", 0.0), other.get("pos_z", 0.0), o_fw, o_fd
                )
                if clearance_box.intersects(other_box):
                    has_collision = True
                    break

            if not has_collision:
                target["rotation"] = new_rotation
                # dimensions stay as pre-rotation (Three.js) — only rotation changes
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

    def _find_item(self, item_id: str, items: list[dict[str, Any]]) -> dict[str, Any] | None:
        for item in items:
            if item.get("id") == item_id or item.get("furniture_id") == item_id:
                return item
        return None

    # Each rule: (dependent_tokens, anchor_tokens, gap_metres).
    # Token matching: dep_tokens must be a subset of the item's token set.
    # Categories come from furniture_id prefix (e.g. "office-chair_01" → "office-chair")
    # so we split on [-_] and match token subsets for robustness.
    _ANCHOR_RULES: list[tuple[frozenset[str], frozenset[str], float]] = [
        (frozenset({"office", "chair"}), frozenset({"desk"}), 0.05),
        (frozenset({"dining", "chair"}), frozenset({"dining", "table"}), 0.05),
        (frozenset({"chair"}), frozenset({"desk"}), 0.05),
        (frozenset({"coffee", "table"}), frozenset({"sofa"}), 0.10),
    ]

    @staticmethod
    def _item_tokens(item: dict[str, Any]) -> frozenset[str]:
        """Lowercase token set from category field (e.g. 'office-chair' → {'office','chair'})."""
        import re

        raw = item.get("category", "") or item.get("id", "")
        return frozenset(t for t in re.split(r"[-_\s]+", raw.lower()) if t)

    def _reanchor_pairs(self, items: list[dict[str, Any]], room: Room) -> int:
        """Re-center dependent items (chairs) on their anchors after repair.

        Determines which side of the anchor the chair is currently closest to,
        snaps it to the correct centred position on that side, and corrects
        the chair's rotation so it faces the anchor.  The snap is skipped if
        it would introduce a new collision with a third item.
        """
        half_w = room.width / 2
        half_d = room.depth / 2
        snapped = 0

        for item in items:
            item_tokens = self._item_tokens(item)

            # Find first matching rule for this item
            matched_anchor_tokens: frozenset[str] | None = None
            matched_gap = 0.05
            for dep_tokens, anc_tokens, gap in self._ANCHOR_RULES:
                if dep_tokens.issubset(item_tokens):
                    matched_anchor_tokens = anc_tokens
                    matched_gap = gap
                    break

            if matched_anchor_tokens is None:
                continue

            # Find anchor candidates by token match
            candidates = [
                a
                for a in items
                if a.get("id") != item.get("id")
                and matched_anchor_tokens.issubset(self._item_tokens(a))
            ]
            if not candidates:
                continue

            cur_x = item.get("pos_x", 0.0)
            cur_z = item.get("pos_z", 0.0)

            # Pick nearest anchor by centre distance
            anchor = min(
                candidates,
                key=lambda a: (
                    (a.get("pos_x", 0.0) - cur_x) ** 2 + (a.get("pos_z", 0.0) - cur_z) ** 2
                ),
            )

            a_fw, a_fd = self._footprint_wh(anchor.get("dimensions", {}), anchor.get("rotation", 0))
            ax = anchor.get("pos_x", 0.0)
            az = anchor.get("pos_z", 0.0)
            gap = matched_gap

            # fw/fd — will be recalculated per side below
            fw_orig = item.get("dimensions", {}).get("width", 0.6)
            fd_orig = item.get("dimensions", {}).get("depth", 0.6)
            cur_rot = item.get("rotation", 0) % 360

            # Determine which side to place the chair using anchor's stored rotation.
            # Matches spatial_resolver.py front_priority = {0:1(south), 180:0(north), 90:2(east), 270:3(west)}
            # Three.js CW: stored=0→south, 90→east, 180→north, 270→west
            # anchor faces its front → chair placed on that same side (in front of anchor)
            #   anchor rot=0   → faces south → chair SOUTH of anchor (side 0)
            #   anchor rot=180 → faces north → chair NORTH of anchor (side 1)
            #   anchor rot=90  → faces east  → chair EAST  of anchor (side 2)
            #   anchor rot=270 → faces west  → chair WEST  of anchor (side 3)
            anchor_rot = anchor.get("rotation", 0) % 360
            anchor_model_offset = anchor.get("model_rotation_offset", 0)
            anchor_effective = (anchor_rot + anchor_model_offset) % 360
            # Use anchor_effective (stored + offset) to determine actual facing direction
            # front_side: 0=south, 1=north, 2=east, 3=west
            _front_side = {0: 0, 90: 2, 180: 1, 270: 3}.get(anchor_effective, 0)

            logger.info(
                f"_reanchor_pairs DEBUG: {item.get('id')} tokens={item_tokens} "
                f"cur=({cur_x:.3f},{cur_z:.3f}) anchor={anchor.get('id')} "
                f"anchor_pos=({ax:.3f},{az:.3f}) anchor_rot={anchor_rot} anchor_eff={anchor_effective} front_side={_front_side} "
                f"a_fw={a_fw:.3f} a_fd={a_fd:.3f}"
            )

            # effective = stored_rotation + model_rotation_offset  (Three.js)
            # effective=0→south, 180→north, 90→west, 270→east
            model_offset = item.get("model_rotation_offset", 0)

            # Build all 4 candidate sides: (facing_rot, fw, fd, cx, cz)
            # facing_rot = stored rotation (no offset) that makes chair face toward anchor.
            # Three.js Y-rotation is CLOCKWISE from above:
            #   stored=0   → faces south (+Z)
            #   stored=90  → faces east  (+X)   [CW 90°]
            #   stored=180 → faces north (-Z)
            #   stored=270 → faces west  (-X)   [CW 270°]
            # Matches spatial_resolver.py _adj(target) where target is the desired facing stored rot.
            # frontend coords: south=higher z (+), north=lower z (-)
            _sides: list[tuple[int, float, float, float, float]] = [
                (
                    180,
                    fw_orig,
                    fd_orig,
                    ax,
                    az + a_fd / 2 + gap + fd_orig / 2,
                ),  # south of anchor → faces north → stored=180
                (
                    0,
                    fw_orig,
                    fd_orig,
                    ax,
                    az - a_fd / 2 - gap - fd_orig / 2,
                ),  # north of anchor → faces south → stored=0
                (
                    270,
                    fd_orig,
                    fw_orig,
                    ax + a_fw / 2 + gap + fd_orig / 2,
                    az,
                ),  # east of anchor  → faces west  → stored=270
                (
                    90,
                    fd_orig,
                    fw_orig,
                    ax - a_fw / 2 - gap - fd_orig / 2,
                    az,
                ),  # west of anchor  → faces east  → stored=90
            ]
            # Always snap to the primary front_side regardless of collision.
            # Placing the chair on a lateral/wrong side is worse than a slight overlap
            # because it makes the arrows face the wrong direction entirely.
            _vrot, _fw, _fd, _cx, _cz = _sides[_front_side]
            _cx = max(-half_w + _fw / 2, min(half_w - _fw / 2, _cx))
            _cz = max(-half_d + _fd / 2, min(half_d - _fd / 2, _cz))
            chosen = (_vrot, _fw, _fd, _cx, _cz)

            facing_rot, fw, fd, best_x, best_z = chosen
            # corrected_rot = stored rotation sent to Three.js
            # effective = stored + model_offset → facing_rot = stored + model_offset
            # → stored = facing_rot - model_offset
            # Matches spatial_resolver.py: stored = _adj(facing_rot) = (facing_rot - offset) % 360
            corrected_rot = (facing_rot - model_offset) % 360

            pos_changed = abs(best_x - cur_x) > 0.01 or abs(best_z - cur_z) > 0.01
            rot_changed = corrected_rot != cur_rot

            if not pos_changed and not rot_changed:
                continue

            logger.info(
                f"_reanchor_pairs: {item.get('id')} "
                f"pos ({cur_x:.3f},{cur_z:.3f})→({best_x:.3f},{best_z:.3f}) "
                f"rot {cur_rot}→{corrected_rot} "
                f"beside {anchor.get('id')}"
            )
            if pos_changed:
                item["pos_x"] = round(best_x, 3)
                item["pos_z"] = round(best_z, 3)
            if rot_changed:
                item["rotation"] = corrected_rot
            snapped += 1

        return snapped
