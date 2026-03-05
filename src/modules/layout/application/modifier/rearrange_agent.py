"""Rearrange Agent — re-plans ALL furniture in an existing layout for feng shui.

Unlike ModifierAgent (which moves one piece), RearrangeAgent takes the full
current_layout, converts it to a furniture_list, asks the LLM to re-plan
positions for every item, then resolves and streams the result.

No catalog selection — every item that was in current_layout comes back.
"""

from __future__ import annotations

import contextlib
import logging
from collections.abc import AsyncGenerator
from typing import Any

from src.modules.layout.application.pipeline.models import (
    Conflict,
    ConflictType,
    SSEEvent,
    SSEEventType,
)
from src.modules.layout.application.pipeline.steps.step4_repair import RepairStep
from src.modules.layout.application.services.furniture_relationships import (
    build_relationship_hints,
)
from src.modules.layout.application.services.layout_resolver import LayoutResolver
from src.modules.layout.domain.entities import Room, RoomType
from src.modules.layout.domain.entities.room import DoorPosition, WallSide, WindowPosition
from src.modules.layout.infrastructure.llm.langchain_agent import (
    FengShuiLLMAgent,
    LLMConfig,
)
from src.modules.layout.infrastructure.llm.prompts import FENG_SHUI_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

_OPPOSITE: dict[str, str] = {
    "north": "south",
    "south": "north",
    "east": "west",
    "west": "east",
}

# Direction keywords for parsing wall constraints from user messages
_DIR_KEYWORDS: dict[str, str] = {
    "ทิศเหนือ": "north",
    "ทิศใต้": "south",
    "ทิศตะวันออก": "east",
    "ทิศตะวันตก": "west",
    "ตะวันออก": "east",
    "ตะวันตก": "west",
    "เหนือ": "north",
    "ใต้": "south",
    "north": "north",
    "south": "south",
    "east": "east",
    "west": "west",
}

_DIR_TH: dict[str, str] = {
    "north": "เหนือ",
    "south": "ใต้",
    "east": "ตะวันออก",
    "west": "ตะวันตก",
}


def _parse_wall_direction(text: str) -> str | None:
    """Extract a compass wall direction from free text. Returns None if not found."""
    lower = text.lower()
    found: list[tuple[int, str]] = []
    for kw, direction in _DIR_KEYWORDS.items():
        idx = lower.find(kw)
        if idx != -1:
            found.append((idx, direction))
    if not found:
        return None
    found.sort()
    return found[0][1]


class RearrangeAgent:
    """Re-plans all furniture in current_layout using the LLM + LayoutResolver.

    Usage:
        agent = RearrangeAgent()
        async for event in agent.apply(current_layout, room_spec, message):
            yield event
    """

    def __init__(self) -> None:
        self._llm_agent = FengShuiLLMAgent(LLMConfig())
        self._resolver = LayoutResolver()

    async def apply(
        self,
        current_layout: list[dict[str, Any]],
        room_spec: dict[str, Any],
        modification_request: str,
    ) -> AsyncGenerator[SSEEvent, None]:
        """Re-plan all furniture and yield SSE events.

        Args:
            current_layout: Existing layout_items list from PipelineState.
            room_spec: Room spec dict (width/depth via dimensions, doors, windows).
            modification_request: The user's original message (for context/explanation).

        Yields:
            SSEEvent objects for streaming.
        """
        yield SSEEvent(
            event_type=SSEEventType.MODIFIER_STARTED,
            data={"modification": modification_request},
        )

        dims = room_spec.get("dimensions") or {}
        room_w = float(room_spec.get("width") or dims.get("width") or 4.0)
        room_d = float(room_spec.get("depth") or dims.get("depth") or 4.0)
        room_type = room_spec.get("room_type", "bedroom")

        yield SSEEvent(
            event_type=SSEEventType.STEP_PROGRESS,
            data={"step": "rearrange", "message": "Analysing furniture...", "progress": 0.15},
        )

        # --- 1. Build furniture_list from current_layout ---
        furniture_list = self._build_furniture_list(current_layout)
        if not furniture_list:
            yield SSEEvent(
                event_type=SSEEventType.MODIFIER_COMPLETED,
                data={
                    "changed_furniture": "all",
                    "collisions_after": 0,
                    "warning": "No furniture found to rearrange",
                },
            )
            return

        logger.info(f"RearrangeAgent: rearranging {len(furniture_list)} items")

        # Track the exact set of furniture IDs that should appear in the output
        allowed_ids: set[str] = {f["id"] for f in furniture_list}

        # --- 2. Build room feature dicts for LLM ---
        raw_doors = room_spec.get("doors") or []
        raw_windows = room_spec.get("windows") or []
        doors = [
            {
                "wall": str(d.get("wall", "")).lower(),
                "offset": float(d.get("offset", 0)),
                "width": float(d.get("width", 0.9)),
            }
            for d in raw_doors
        ]
        windows = [
            {
                "wall": str(w.get("wall", "")).lower(),
                "offset": float(w.get("offset", 0)),
                "width": float(w.get("width", 1.0)),
            }
            for w in raw_windows
        ]
        command_positions = self._build_command_positions(doors)

        yield SSEEvent(
            event_type=SSEEventType.STEP_PROGRESS,
            data={"step": "rearrange", "message": "Planning feng shui layout...", "progress": 0.40},
        )

        # --- 3. Call LLM to re-plan ---
        owned_ids_str = ", ".join(sorted(allowed_ids))

        # Build inter-furniture relationship hints so the LLM knows
        # TV should face sofa, nightstand beside bed, etc.
        rel_hints = build_relationship_hints(furniture_list)
        rel_hints_str = "\n".join(f"- {h}" for h in rel_hints) if rel_hints else ""
        logger.info(f"RearrangeAgent: {len(rel_hints)} relationship hints generated")

        # Detect explicit wall direction in user message (e.g. "ไปฝั่งเหนือทั้งหมด")
        wall_dir = _parse_wall_direction(modification_request)
        logger.info(f"RearrangeAgent: parsed wall_dir={wall_dir!r} from {modification_request!r}")

        wall_constraint = ""
        if wall_dir:
            dir_th = _DIR_TH.get(wall_dir, wall_dir)
            wall_constraint = (
                f"CRITICAL USER INSTRUCTION: Place ALL furniture against the {wall_dir.upper()} wall. "
                f'Every item must have target_wall="{wall_dir}" and offset_from_wall=0.05. '
                f"(User said: place everything toward the {dir_th} side.)"
            )
            logger.info(f"RearrangeAgent: injecting wall_constraint={wall_constraint!r}")

        hard_constraints = (
            f"You MUST place ALL {len(furniture_list)} of these furniture IDs — every single one: [{owned_ids_str}]. "
            "Do NOT skip, drop, or omit any item from the list. "
            "Do NOT add, rename, or invent any furniture not in this list. "
            f"Your response MUST contain exactly {len(furniture_list)} placements."
        )
        if wall_constraint:
            hard_constraints += f"\n{wall_constraint}"

        user_prefs: dict[str, Any] = {
            "user_message": modification_request,
            "owned_furniture": owned_ids_str,
            "placement_constraints": hard_constraints,
        }
        if rel_hints_str:
            user_prefs["furniture_relationships"] = (
                "IMPORTANT — spatial relationships between items (MUST follow these):\n"
                + rel_hints_str
            )

        llm_response = await self._llm_agent.plan_layout(
            room_type=room_type,
            width=room_w,
            depth=room_d,
            usable_area=room_w * room_d * 0.7,
            doors=doors,
            windows=windows,
            furniture_list=furniture_list,
            command_positions=command_positions,
            user_preferences=user_prefs,
        )

        if not llm_response.success:
            logger.warning(f"RearrangeAgent: LLM plan_layout failed: {llm_response.error}")
            yield SSEEvent(
                event_type=SSEEventType.MODIFIER_COMPLETED,
                data={
                    "changed_furniture": "all",
                    "collisions_after": 0,
                    "warning": f"LLM planning failed: {llm_response.error}",
                },
            )
            return

        yield SSEEvent(
            event_type=SSEEventType.STEP_PROGRESS,
            data={"step": "rearrange", "message": "Resolving positions...", "progress": 0.70},
        )

        # --- 4. Resolve semantic → physical ---
        placements = (
            llm_response.content.get("placements", [])
            if isinstance(llm_response.content, dict)
            else []
        )
        # Override LLM-reported sizes with actual furniture dimensions from current_layout
        # to prevent furniture from using wrong/hallucinated sizes.
        dims_by_id = {
            item.get("furniture_id", item.get("id", "")): item.get("dimensions", {})
            for item in current_layout
        }
        corrected_placements = []
        # Alignments to distribute items along the wall when packing everything there
        _pack_alignments = ["left", "center", "right", "left", "center", "right"]
        for idx, p in enumerate(placements):
            fid = p.get("furniture_id", "")
            real_dims = dims_by_id.get(fid) or {}
            w = real_dims.get("width") or real_dims.get("w")
            d = real_dims.get("depth") or real_dims.get("l")
            h = real_dims.get("height") or real_dims.get("h")
            if w:
                # Always override with actual dims — prevents hallucinated LLM sizes
                p = dict(p)
                p["size"] = {
                    "w": float(w),
                    "l": float(d or w),
                    "h": float(h or 1.0),
                }
            # If user explicitly requested a wall direction, force it on every item
            if wall_dir:
                p = dict(p)
                p["target_wall"] = wall_dir
                p["offset_from_wall"] = 0.05
                # Distribute alignments to avoid LLM putting everything at "center"
                p["alignment"] = _pack_alignments[idx % len(_pack_alignments)]
            corrected_placements.append(p)
        resolution = self._resolver.resolve(corrected_placements, room_spec)

        # --- 4b. Repair collisions with RepairStep shift logic ---
        collisions = resolution.collisions
        physical = list(resolution.physical_placements)
        if collisions:
            room_obj = self._build_room(room_spec)
            repair = RepairStep.__new__(RepairStep)  # no pipeline config needed
            _MAX_REPAIR = 5
            for _attempt in range(_MAX_REPAIR):
                if not collisions:
                    break
                for c in collisions:
                    ids = c.get("furniture_ids", [])
                    if not ids:
                        continue
                    conflict = Conflict(
                        conflict_type=ConflictType.OVERLAP,
                        description=c.get("description", "overlap"),
                        items_involved=ids,
                    )
                    repair._try_shift(conflict, physical, room_obj)
                # Re-check by re-resolving (use same semantics, just update positions)
                collisions = self._recheck_collisions(physical, room_obj)

        yield SSEEvent(
            event_type=SSEEventType.STEP_PROGRESS,
            data={"step": "rearrange", "message": "Finalising...", "progress": 0.90},
        )

        # --- 5. Enrich with metadata from current_layout ---
        enriched = self._enrich_from_current(physical, current_layout)

        # Filter to only IDs that were in the original layout (LLM may hallucinate extras)
        enriched = [e for e in enriched if e.get("furniture_id", e.get("id", "")) in allowed_ids]

        # Backfill any items the LLM dropped — try to find a collision-free spot first
        placed_ids = {e.get("furniture_id", e.get("id", "")) for e in enriched}
        for original in current_layout:
            fid = original.get("furniture_id", original.get("id", ""))
            if fid and fid not in placed_ids:
                logger.warning(
                    f"RearrangeAgent: LLM dropped {fid!r} — attempting to place collision-free"
                )
                # Try original position first; if it collides, shift until free
                room_obj = self._build_room(room_spec)
                candidate = dict(original)
                conflict = Conflict(
                    conflict_type=ConflictType.OVERLAP,
                    description=f"backfill {fid}",
                    items_involved=[fid],
                )
                repair = RepairStep.__new__(RepairStep)
                # Check if original position already collides with placed items
                from src.modules.layout.infrastructure.geometry import AABB

                dims = original.get("dimensions", {})
                rot = original.get("rotation", 0)
                fw = float(dims.get("width", 1.0))
                fd = float(dims.get("depth", 1.0))
                if rot % 360 in (90, 270):
                    fw, fd = fd, fw
                orig_box = AABB.from_center_and_size(
                    original.get("pos_x", 0.0), original.get("pos_z", 0.0), fw, fd
                )
                def _other_box(e: dict[str, Any]) -> AABB:
                    ed = e.get("dimensions", {})
                    ew = float(ed.get("width", 1.0))
                    efd = float(ed.get("depth", 1.0))
                    if e.get("rotation", 0) % 360 in (90, 270):
                        ew, efd = efd, ew
                    return AABB.from_center_and_size(e.get("pos_x", 0.0), e.get("pos_z", 0.0), ew, efd)

                has_collision = any(
                    orig_box.intersects(_other_box(e))
                    for e in enriched
                    if e.get("furniture_id", e.get("id", "")) != fid
                )
                if has_collision:
                    # Add as temporary item so _try_shift can shift it away from others
                    enriched.append(candidate)
                    action = repair._try_shift(conflict, enriched, room_obj)
                    if not (action and action.success):
                        logger.warning(
                            f"RearrangeAgent: could not find free spot for {fid!r} — using original"
                        )
                else:
                    enriched.append(candidate)

        yield SSEEvent(
            event_type=SSEEventType.MODIFIER_UPDATED,
            data={"items": enriched},
        )

        # --- 6. Generate explanation ---
        explanation = await self._generate_explanation(
            room_type=room_type,
            width=room_w,
            depth=room_d,
            item_count=len(enriched),
            modification_request=modification_request,
            collisions_remaining=len(collisions),
            feng_shui_score=resolution.deterministic_score,
        )

        yield SSEEvent(
            event_type=SSEEventType.MODIFIER_COMPLETED,
            data={
                "changed_furniture": "all",
                "placed_count": len(enriched),
                "collisions_after": len(collisions),
                "deterministic_score": resolution.deterministic_score,
                "layout_items": enriched,
                "explanation": explanation,
            },
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_furniture_list(current_layout: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Convert current_layout items to the format expected by plan_layout()."""
        result = []
        for item in current_layout:
            dims = item.get("dimensions") or {}
            fid = item.get("furniture_id") or item.get("id") or ""
            if not fid:
                continue
            result.append(
                {
                    "id": fid,
                    "name": item.get("name", fid),
                    "width": float(dims.get("width", 1.0)),
                    "depth": float(dims.get("depth", 1.0)),
                    "height": float(dims.get("height", 1.0)),
                    "is_essential": item.get("is_essential", True),
                }
            )
        return result

    @staticmethod
    def _build_command_positions(doors: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Derive feng shui command positions from doors (same logic as step2)."""
        command_positions = []
        for door in doors:
            door_wall = str(door.get("wall", "")).lower()
            command_wall = _OPPOSITE.get(door_wall)
            if command_wall:
                command_positions.append(
                    {
                        "wall": command_wall,
                        "reason": f"diagonal from {door_wall} door — command position",
                    }
                )
        return command_positions

    @staticmethod
    def _enrich_from_current(
        physical: list[dict[str, Any]],
        current_layout: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Copy name/category/is_essential/model_url from current_layout into new placements."""
        catalog: dict[str, dict[str, Any]] = {
            item.get("furniture_id", item.get("id", "")): item for item in current_layout
        }
        result = []
        for item in physical:
            fid = item.get("furniture_id", item.get("id", ""))
            src = catalog.get(fid, {})
            # Use original dimensions from current_layout — Three.js needs pre-rotation
            # dims so that BoxGeometry(w, h, d) + group.rotation gives correct shape.
            # The resolved item's dimensions are post-rotation footprint sizes which
            # would cause wrong rendering when rotation != 0.
            original_dims = (
                src.get("dimensions")
                or item.get("dimensions")
                or {"width": 1.0, "depth": 1.0, "height": 1.0}
            )
            enriched: dict[str, Any] = {
                **item,
                "name": src.get("name", item.get("name", fid)),
                "category": src.get("category", item.get("category", fid.split("_")[0])),
                "is_essential": src.get("is_essential", item.get("is_essential", True)),
                "dimensions": original_dims,
                "feng_shui_notes": src.get("feng_shui_notes", ""),
            }
            model_url = src.get("model_url") or item.get("model_url")
            if model_url:
                enriched["model_url"] = model_url
            # Preserve model_rotation_offset so renderer knows model's forward direction
            mro = src.get("model_rotation_offset") or item.get("model_rotation_offset")
            if mro:
                enriched["model_rotation_offset"] = int(mro)
            result.append(enriched)
        return result

    @staticmethod
    def _build_room(room_spec: dict[str, Any]) -> Room:
        """Build a Room domain object from room_spec dict."""
        dims = room_spec.get("dimensions") or {}
        width = float(room_spec.get("width") or dims.get("width") or 4.0)
        depth = float(room_spec.get("depth") or dims.get("depth") or 4.0)
        height = float(room_spec.get("height") or dims.get("height") or 2.8)
        room_type_str = room_spec.get("room_type", "bedroom")
        try:
            room_type = RoomType(room_type_str)
        except ValueError:
            room_type = RoomType.BEDROOM
        doors = []
        for d in room_spec.get("doors") or []:
            with contextlib.suppress(KeyError, ValueError):
                doors.append(
                    DoorPosition(
                        wall=WallSide(d["wall"]),
                        offset=float(d.get("offset", 0)),
                        width=float(d.get("width", 0.9)),
                    )
                )
        windows = []
        for w in room_spec.get("windows") or []:
            with contextlib.suppress(KeyError, ValueError):
                windows.append(
                    WindowPosition(
                        wall=WallSide(w["wall"]),
                        offset=float(w.get("offset", 0)),
                        width=float(w.get("width", 1.0)),
                    )
                )
        return Room(
            width=width,
            depth=depth,
            height=height,
            room_type=room_type,
            doors=doors,
            windows=windows,
        )

    @staticmethod
    def _recheck_collisions(physical: list[dict[str, Any]], room: Room) -> list[dict[str, Any]]:
        """Naive AABB overlap check on physical items (centre-based coords)."""
        from src.modules.layout.infrastructure.geometry import AABB

        def footprint(item: dict[str, Any]) -> tuple[float, float]:
            # dimensions store pre-rotation values (for Three.js BoxGeometry).
            # _physical_to_dict swaps width/depth for 90/270° so rendering is correct.
            # We swap again here to get actual room-space footprint extents.
            dims = item.get("dimensions", {})
            w = float(dims.get("width", 1.0))
            d = float(dims.get("depth", 1.0))
            rot = item.get("rotation", 0)
            if rot % 360 in (90, 270):
                return d, w
            return w, d

        collisions = []
        for i, a in enumerate(physical):
            for b in physical[i + 1 :]:
                fw_a, fd_a = footprint(a)
                fw_b, fd_b = footprint(b)
                box_a = AABB.from_center_and_size(a.get("pos_x", 0), a.get("pos_z", 0), fw_a, fd_a)
                box_b = AABB.from_center_and_size(b.get("pos_x", 0), b.get("pos_z", 0), fw_b, fd_b)
                if box_a.intersects(box_b):
                    id_a = a.get("furniture_id", a.get("id", ""))
                    id_b = b.get("furniture_id", b.get("id", ""))
                    collisions.append(
                        {"furniture_ids": [id_a, id_b], "description": f"{id_a} overlaps {id_b}"}
                    )
        return collisions

    async def _generate_explanation(
        self,
        room_type: str,
        width: float,
        depth: float,
        item_count: int,
        modification_request: str,
        collisions_remaining: int,
        feng_shui_score: int,
    ) -> str:
        """Generate a Thai explanation of the rearranged layout."""
        from langchain_core.messages import HumanMessage, SystemMessage

        prompt = (
            f"You just rearranged ALL {item_count} furniture pieces in a {room_type} "
            f"({width}m × {depth}m) for feng shui.\n"
            f'User request: "{modification_request}"\n'
            f"Feng shui score: {feng_shui_score}/70\n"
            f"Remaining collisions: {collisions_remaining}\n\n"
            "Write a short confirmation in Thai (60–100 words) that:\n"
            "1. Confirms ALL furniture has been rearranged for feng shui\n"
            "2. Mentions the key feng shui principle applied (command position, chi flow, etc.)\n"
            "3. States the feng shui score briefly\n"
            "4. If collisions remain, mention it\n"
            "Write in plain, warm Thai prose only. No JSON, no bullet lists."
        )
        try:
            response = await self._llm_agent._llm.ainvoke(
                [
                    SystemMessage(content=FENG_SHUI_SYSTEM_PROMPT),
                    HumanMessage(content=prompt),
                ]
            )
            return str(response.content).strip()
        except Exception as exc:
            logger.warning(f"RearrangeAgent: explanation LLM call failed: {exc}")
            score_label = (
                "ดีมาก" if feng_shui_score >= 55 else ("ดี" if feng_shui_score >= 35 else "พอใช้")
            )
            return (
                f"จัดวางเฟอร์นิเจอร์ทั้งหมดใหม่ตามหลักฮวงจุ้ยเรียบร้อยแล้วค่ะ "
                f"คะแนนฮวงจุ้ย {feng_shui_score}/70 ({score_label})"
            )
