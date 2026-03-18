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
from src.modules.layout.application.services.wall_assigner import WallAssigner
from src.modules.layout.application.services.layout_resolver import LayoutResolver
from src.modules.layout.domain.entities import Room, RoomType
from src.modules.layout.domain.entities.room import DoorPosition, WallSide, WindowPosition
from src.modules.layout.infrastructure.tools.furniture_catalog_data import FURNITURE_CATALOG
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
        logger.info(f"RearrangeAgent: room_spec keys={list(room_spec.keys())} room_w={room_w} room_d={room_d}")

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

        # --- 2. Build room feature dicts ---
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

        # --- 3. Call LLM to re-plan (simplified: LLM only assigns priority + type) ---
        owned_ids_str = ", ".join(sorted(allowed_ids))

        # Detect explicit wall direction in user message (e.g. "ไปฝั่งเหนือทั้งหมด")
        wall_dir = _parse_wall_direction(modification_request)
        logger.info(f"RearrangeAgent: parsed wall_dir={wall_dir!r} from {modification_request!r}")

        hard_constraints = (
            f"You MUST place ALL {len(furniture_list)} of these furniture IDs — every single one: [{owned_ids_str}]. "
            "Do NOT skip, drop, or omit any item from the list. "
            f"Your response MUST contain exactly {len(furniture_list)} placements."
        )

        user_prefs: dict[str, Any] = {
            "user_message": modification_request,
            "owned_furniture": owned_ids_str,
            "placement_constraints": hard_constraints,
        }

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
        for p in placements:
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
            # Fill defaults for fields the simplified LLM no longer provides
            p = dict(p)
            p.setdefault("target_wall", "center")
            p.setdefault("alignment", "center")
            p.setdefault("offset_from_wall", 0.05)
            corrected_placements.append(p)

        # WallAssigner handles wall placement deterministically
        # If user explicitly requested a wall direction, override after assignment
        wall_assigner = WallAssigner()
        corrected_placements = wall_assigner.assign(corrected_placements, room_spec)

        if wall_dir:
            _pack_alignments = ["left", "center", "right", "left", "center", "right"]
            for idx, p in enumerate(corrected_placements):
                p = dict(p)
                p["target_wall"] = wall_dir
                p["offset_from_wall"] = 0.0
                p["alignment"] = _pack_alignments[idx % len(_pack_alignments)]
                corrected_placements[idx] = p

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
        logger.info(f"RearrangeAgent: physical before enrich: " + ", ".join(
            f"{p.get('furniture_id','?')}=({p.get('pos_x','?')},{p.get('pos_z','?')})"
            for p in physical
        ))
        enriched = self._enrich_from_current(physical, current_layout)

        # Filter to only IDs that were in the original layout (LLM may hallucinate extras)
        enriched = [e for e in enriched if e.get("furniture_id", e.get("id", "")) in allowed_ids]

        # Backfill any items the LLM dropped — re-resolve paired items so they get
        # placed beside their anchor; fall back to collision-free shift for others.
        _DEPENDENT_TYPES = {"chair", "office_chair", "dining_chair", "coffee_table"}
        placed_ids = {e.get("furniture_id", e.get("id", "")) for e in enriched}
        for original in current_layout:
            fid = original.get("furniture_id", original.get("id", ""))
            if fid and fid not in placed_ids:
                logger.warning(
                    f"RearrangeAgent: LLM dropped {fid!r} — attempting to place collision-free"
                )
                ftype = original.get("furniture_type", original.get("category", "")).lower().replace("-", "_")

                # For paired items (chair beside desk, etc.) re-run resolver so
                # _place_beside_anchor can position and orient it correctly.
                if ftype in _DEPENDENT_TYPES:
                    # Build a minimal semantic placement for this item using the
                    # current wall assignment from the original item.
                    dims = original.get("dimensions", {})
                    synthetic_plan = [{
                        "furniture_id": fid,
                        "furniture_type": ftype,
                        "size": {
                            "w": float(dims.get("width", 0.6)),
                            "l": float(dims.get("depth", 0.6)),
                            "h": float(dims.get("height", 1.0)),
                        },
                        "target_wall": original.get("wall", "south"),
                        "alignment": "center",
                        "offset_from_wall": 0.05,
                        "priority": 99,
                        "orientation": "",
                        "facing": "",
                    }]
                    # Include anchor items already placed so resolver can pair them
                    anchor_plan = []
                    for e in enriched:
                        eid = e.get("furniture_id", e.get("id", ""))
                        etype = e.get("furniture_type", e.get("category", "")).lower().replace("-", "_")
                        edims = e.get("dimensions", {})
                        anchor_plan.append({
                            "furniture_id": eid,
                            "furniture_type": etype,
                            "size": {
                                "w": float(edims.get("width", 1.0)),
                                "l": float(edims.get("depth", 1.0)),
                                "h": float(edims.get("height", 1.0)),
                            },
                            "target_wall": e.get("wall", "south"),
                            "alignment": "center",
                            "offset_from_wall": 0.05,
                            "priority": 1,
                            "orientation": "",
                            "facing": "",
                        })
                    try:
                        re_result = self._resolver.resolve(anchor_plan + synthetic_plan, room_spec)
                        for ph in re_result.physical_placements:
                            if ph.get("furniture_id", ph.get("id", "")) == fid:
                                candidate = {**original, **ph}
                                enriched.append(candidate)
                                logger.info(f"RearrangeAgent: re-resolved {fid!r} via pairing at rot={ph.get('rotation')}")
                                break
                        else:
                            enriched.append(dict(original))
                    except Exception as exc:
                        logger.warning(f"RearrangeAgent: re-resolve failed for {fid!r}: {exc} — using original")
                        enriched.append(dict(original))
                    continue

                # Non-paired items: try original position; shift if colliding
                room_obj = self._build_room(room_spec)
                candidate = dict(original)
                conflict = Conflict(
                    conflict_type=ConflictType.OVERLAP,
                    description=f"backfill {fid}",
                    items_involved=[fid],
                )
                repair = RepairStep.__new__(RepairStep)
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
                    enriched.append(candidate)
                    action = repair._try_shift(conflict, enriched, room_obj)
                    if not (action and action.success):
                        logger.warning(
                            f"RearrangeAgent: could not find free spot for {fid!r} — using original"
                        )
                else:
                    enriched.append(candidate)

        # Re-center chairs/dependent items on their anchors.
        # Done after enrich so model_rotation_offset is available for rotation correction.
        logger.info(
            "RearrangeAgent: enriched positions before _reanchor_pairs: "
            + ", ".join(
                f"{e.get('furniture_id', e.get('id','?'))}=({e.get('pos_x',0):.3f},{e.get('pos_z',0):.3f})"
                for e in enriched
            )
        )
        _reanchor_repair = RepairStep.__new__(RepairStep)
        _reanchored = _reanchor_repair._reanchor_pairs(enriched, self._build_room(room_spec))
        if _reanchored:
            logger.info(f"RearrangeAgent: re-anchored {_reanchored} dependent item(s)")

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
            room_spec=room_spec,
            enriched_layout=enriched,
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
            logger.info(
                f"_enrich_from_current: {fid} item.pos_x={item.get('pos_x','MISSING')} "
                f"src.pos_x={src.get('pos_x','NONE')} src.keys={list(src.keys())[:8]}"
            )
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
            # Look up model_rotation_offset from catalog by furniture_type
            ftype = item.get("furniture_type") or src.get("furniture_type") or src.get("category") or ""
            ftype_norm = ftype.lower().replace("-", "_").replace(" ", "_")
            catalog_entry = next(
                (c for c in FURNITURE_CATALOG
                 if c.category.value == ftype_norm
                 or c.id.startswith(ftype_norm)
                 or ftype_norm.startswith(c.category.value)),
                None,
            )
            mro = (
                catalog_entry.model_rotation_offset
                if catalog_entry is not None
                else src.get("model_rotation_offset") or item.get("model_rotation_offset", 0)
            )
            enriched["model_rotation_offset"] = int(mro) if mro is not None else 0
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
        room_spec: dict[str, Any] | None = None,
        enriched_layout: list[dict[str, Any]] | None = None,
    ) -> str:
        """Generate a Thai explanation of the rearranged layout."""
        from src.modules.layout.application.services.kua_calculator import (
            calculate_kua,
            detect_kua_priority,
            kua_best_direction_info,
        )
        from src.modules.layout.infrastructure.llm.prompts import EXPLANATION_PROMPT
        from src.modules.layout.application.agent.personality import get_system_prompt
        from langchain_core.messages import HumanMessage, SystemMessage

        # Build kua_line — pre-rendered Thai text, no LLM logic needed
        kua_line = "ลองกรอกปีเกิดและเพศในการตั้งค่าห้อง เพื่อให้เราปรับทิศหัวเตียงตามเลขกัวส่วนตัวของคุณได้"
        if room_spec:
            user_prefs = room_spec.get("user_preferences") or {}
            birth_year = user_prefs.get("birth_year")
            gender = user_prefs.get("gender", "")
            logger.info(f"RearrangeAgent: _generate_explanation user_prefs={user_prefs!r}")
            if birth_year and gender:
                try:
                    kua = calculate_kua(int(birth_year), gender)
                    priority = detect_kua_priority(modification_request)
                    info = kua_best_direction_info(kua, priority)
                    # Find actual bed wall from enriched layout
                    actual_bed_wall = None
                    if enriched_layout:
                        actual_bed_wall = next(
                            (
                                e.get("wall") or e.get("target_wall")
                                for e in enriched_layout
                                if (e.get("category") or "").lower() in ("bed", "sofa_bed")
                                or "bed" in (e.get("furniture_id") or "").lower()
                            ),
                            None,
                        )
                    _wall_th = {"north": "เหนือ", "south": "ใต้", "east": "ตะวันออก", "west": "ตะวันตก"}
                    if actual_bed_wall and actual_bed_wall != info["wall"]:
                        actual_wall_th = _wall_th.get(actual_bed_wall, actual_bed_wall)
                        kua_line = (
                            f"อยากเสริม{info['benefit']} แต่ทิศ{info['wall_th']}ติดประตู "
                            f"จึงจัดหัวเตียงไว้ทิศ{actual_wall_th}ซึ่งเป็นทิศมงคลรองของเลขกัว {kua} แทน"
                        )
                    else:
                        kua_line = f"หัวเตียงหันทิศ{info['wall_th']}ตามเลขกัว {kua} เสริม{info['benefit']}ให้คุณโดยตรง"
                except Exception as e:
                    logger.warning(f"RearrangeAgent: kua_line build failed: {e}")

        logger.info(f"RearrangeAgent: kua_line={kua_line!r}")

        grade = "ดีมาก" if feng_shui_score >= 55 else ("ดี" if feng_shui_score >= 35 else "พอใช้")

        prompt = EXPLANATION_PROMPT.format(
            total_score=feng_shui_score,
            grade=grade,
            remaining_issues="ไม่มี" if collisions_remaining == 0 else f"{collisions_remaining} จุดชนกัน",
            kua_line=kua_line,
        )

        try:
            system_prompt = get_system_prompt("buddy")
            response = await self._llm_agent._llm.ainvoke(
                [
                    SystemMessage(content=system_prompt),
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
