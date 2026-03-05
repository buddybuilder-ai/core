"""Modifier Agent — applies incremental layout changes requested by the user.

Process:
1. Identify the target furniture item from extracted_params.
2. Back-convert all existing physical placements to semantic format.
3. Override the target's orientation hint with the modification request.
4. Re-run FengShuiLLMAgent.plan_layout() so the LLM re-plans placements.
5. Resolve semantic → physical via LayoutResolver.
6. Simple nudge-repair for any remaining collisions (max 3 attempts).
7. Stream SSEEvents throughout.

No full pipeline re-run — only steps 2-4 (plan + resolve + lightweight repair).
"""

from __future__ import annotations

import logging
import re
from collections.abc import AsyncGenerator
from typing import Any

from src.modules.layout.application.pipeline.models import (
    SSEEvent,
    SSEEventType,
)
from src.modules.layout.application.services.layout_resolver import LayoutResolver
from src.modules.layout.infrastructure.llm.langchain_agent import (
    FengShuiLLMAgent,
    LLMConfig,
)
from src.modules.layout.infrastructure.llm.prompts import (
    FENG_SHUI_SYSTEM_PROMPT,
    MODIFIER_EXPLANATION_PROMPT,
)

logger = logging.getLogger(__name__)

# Maximum nudge attempts when collisions remain after modification
_MAX_REPAIR_ATTEMPTS = 6
# Distance to shift item along its wall per repair attempt (meters)
_NUDGE_DISTANCE = 0.3


class ModifierAgent:
    """Applies a single modification to an existing layout.

    Usage:
        agent = ModifierAgent()
        async for event in agent.apply(current_layout, room_spec, message, params):
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
        extracted_params: dict[str, Any],
    ) -> AsyncGenerator[SSEEvent, None]:
        """Apply a modification and yield SSE events.

        Args:
            current_layout: Existing layout_items list from PipelineState.
            room_spec: Room spec dict (width, depth, doors, windows).
            modification_request: The user's original message.
            extracted_params: Router-extracted {action, target_furniture, details}.

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
        target_type = str(extracted_params.get("target_furniture", "")).lower()

        # --- 1. Build semantic placements from existing physical layout ---
        yield SSEEvent(
            event_type=SSEEventType.STEP_PROGRESS,
            data={"step": "modifier", "message": "Analysing current layout...", "progress": 0.2},
        )

        semantic_placements = self._layout_to_semantics(
            current_layout, room_w, room_d, target_type, modification_request, room_spec
        )

        if not semantic_placements:
            yield SSEEvent(
                event_type=SSEEventType.MODIFIER_COMPLETED,
                data={
                    "changed_furniture": target_type,
                    "collisions_after": 0,
                    "warning": "No furniture found to modify",
                },
            )
            return

        logger.info(
            f"🔧 ModifierAgent: modifying {target_type!r}, "
            f"{len(semantic_placements)} placements total"
        )
        for sp in semantic_placements:
            logger.debug(
                f"  semantic: {sp.get('furniture_id')} wall={sp.get('target_wall')} "
                f"align={sp.get('alignment')} offset={sp.get('offset_from_wall')}"
            )

        # --- 2. Resolve only the target item; keep non-targets at their current positions ---
        # Split semantics: target (priority=0) vs bystanders
        target_semantics = [s for s in semantic_placements if s.get("priority") == 0]
        non_target_ids = {
            s.get("furniture_id") for s in semantic_placements if s.get("priority") != 0
        }

        yield SSEEvent(
            event_type=SSEEventType.STEP_PROGRESS,
            data={"step": "modifier", "message": "Resolving positions...", "progress": 0.65},
        )

        # --- 3. Resolve semantic → physical (target only) ---
        resolution = self._resolver.resolve(target_semantics, room_spec)
        physical_target = list(resolution.physical_placements)

        # Non-target items: copy directly from current_layout without re-resolving
        enriched_others = [
            item for item in current_layout
            if item.get("furniture_id", item.get("id", "")) in non_target_ids
        ]

        # Build enriched target item(s)
        enriched_target = self._enrich_from_current(physical_target, current_layout)

        # Merge: target first, then bystanders in their original order
        enriched = enriched_target + enriched_others

        # --- 4. Collision check against ALL items (target + bystanders) ---
        # Recheck collisions between target and bystanders using the full enriched list
        from src.modules.layout.application.modifier.rearrange_agent import RearrangeAgent
        from src.modules.layout.application.pipeline.models import Conflict, ConflictType
        from src.modules.layout.application.pipeline.steps.step4_repair import RepairStep
        from src.modules.layout.infrastructure.geometry import AABB

        room_obj = RearrangeAgent._build_room(room_spec)
        collisions = RearrangeAgent._recheck_collisions(enriched, room_obj)

        for attempt in range(_MAX_REPAIR_ATTEMPTS):
            if not collisions:
                break
            logger.debug(
                f"ModifierAgent: repair attempt {attempt + 1}, {len(collisions)} collisions"
            )
            repair = RepairStep.__new__(RepairStep)
            for c in collisions:
                ids = c.get("furniture_ids", [])
                # Only shift the target — never move bystanders
                target_id = next(
                    (fid for fid in ids if fid not in non_target_ids), None
                )
                if not target_id:
                    continue
                conflict = Conflict(
                    conflict_type=ConflictType.OVERLAP,
                    description=c.get("description", "overlap"),
                    items_involved=[target_id],
                )
                repair._try_shift(conflict, enriched, room_obj)
            collisions = RearrangeAgent._recheck_collisions(enriched, room_obj)

        physical = physical_target

        yield SSEEvent(
            event_type=SSEEventType.STEP_PROGRESS,
            data={"step": "modifier", "message": "Finalising...", "progress": 0.9},
        )

        yield SSEEvent(
            event_type=SSEEventType.MODIFIER_UPDATED,
            data={"items": enriched},
        )

        # Look up target item from semantics using token-based matching to avoid
        # false positives (e.g. "bed" matching "bedside_table" or "sofa-bed").
        def _tokens(s: str) -> set[str]:
            return set(re.split(r"[-_\s]+", s.lower()))

        target_semantic = next(
            (
                s
                for s in target_semantics
                if target_type in _tokens(s.get("furniture_id", ""))
                or target_type in _tokens(s.get("furniture_type", ""))
            ),
            target_semantics[0] if target_semantics else {},
        )
        dims = room_spec.get("dimensions") or {}
        doors = room_spec.get("doors", [])
        door_wall = str(doors[0].get("wall", "unknown")).lower() if doors else "unknown"
        room_type = room_spec.get("room_type", "room")
        new_wall = target_semantic.get("target_wall", "unknown")
        alignment = target_semantic.get("alignment", "center")
        offset = float(target_semantic.get("offset_from_wall", 0.0))

        yield SSEEvent(
            event_type=SSEEventType.STEP_PROGRESS,
            data={"step": "modifier", "message": "Generating explanation...", "progress": 0.95},
        )

        explanation = await self._generate_explanation(
            room_type=room_type,
            width=float(room_spec.get("width") or dims.get("width") or room_w),
            depth=float(room_spec.get("depth") or dims.get("depth") or room_d),
            door_wall=door_wall,
            modification_request=modification_request,
            target_furniture=target_type,
            new_wall=new_wall,
            alignment=alignment,
            offset=offset,
            collisions_remaining=len(collisions),
        )

        yield SSEEvent(
            event_type=SSEEventType.MODIFIER_COMPLETED,
            data={
                "changed_furniture": target_type,
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

    async def _generate_explanation(
        self,
        room_type: str,
        width: float,
        depth: float,
        door_wall: str,
        modification_request: str,
        target_furniture: str,
        new_wall: str,
        alignment: str,
        offset: float,
        collisions_remaining: int,
    ) -> str:
        """Ask the LLM to explain why the furniture was moved there."""
        from langchain_core.messages import HumanMessage, SystemMessage

        prompt = MODIFIER_EXPLANATION_PROMPT.format(
            room_type=room_type,
            width=width,
            depth=depth,
            door_wall=door_wall,
            modification_request=modification_request,
            target_furniture=target_furniture,
            new_wall=new_wall,
            alignment=alignment,
            offset=offset,
            collisions_remaining=collisions_remaining,
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
            logger.warning(f"ModifierAgent: explanation LLM call failed: {exc}")
            wall_th = {
                "north": "ผนังด้านเหนือ",
                "south": "ผนังด้านใต้",
                "east": "ผนังด้านตะวันออก",
                "west": "ผนังด้านตะวันตก",
                "center": "กลางห้อง",
            }.get(new_wall, new_wall)
            return f"ขยับ{target_furniture}ไปที่{wall_th}แล้วค่ะ ตามหลักฮ้วงจุ้ยตำแหน่งนี้เหมาะสมกับห้องนี้"

    _OPPOSITE: dict[str, str] = {
        "north": "south",
        "south": "north",
        "east": "west",
        "west": "east",
    }

    # Direction keywords: keyword → compass direction name
    # Longer keywords must come before shorter ones so find() matches the right position.
    _DIR_KEYWORDS: dict[str, str] = {
        # Thai — long forms first
        "ทิศเหนือ": "north",
        "ทิศใต้": "south",
        "ทิศตะวันออก": "east",
        "ทิศตะวันตก": "west",
        "ตะวันออก": "east",
        "ตะวันตก": "west",
        # Thai short-form colloquial (กำแพงออก = east wall, กำแพงตก = west wall)
        "เหนือ": "north",
        "ใต้": "south",
        "ทิศออก": "east",
        "ทิศตก": "west",
        # "ออก"/"ตก" alone — must NOT shadow Thai words ending in these syllables,
        # so we use the prefix " ออก"/" ตก" (with space) to avoid false matches.
        # These are added AFTER longer keywords to serve as fallback only.
        "กำแพงออก": "east",
        "กำแพงตก": "west",
        "ผนังออก": "east",
        "ผนังตก": "west",
        "กลางห้อง": "center",
        "กลาง": "center",
        # English full
        "north": "north",
        "south": "south",
        "east": "east",
        "west": "west",
        "center": "center",
        "centre": "center",
        # Abbreviations after "ทิศ" (e.g. "ทิศ N", "ทิศ n")
        "ทิศ n": "north",
        "ทิศ s": "south",
        "ทิศ e": "east",
        "ทิศ w": "west",
        "middle": "center",
    }

    # Explicit alignment keywords in hint → override alignment directly
    _ALIGNMENT_KEYWORDS: dict[str, str] = {
        # Thai
        "มุมขวา": "right",
        "ด้านขวา": "right",
        "ขวา": "right",
        "มุมซ้าย": "left",
        "ด้านซ้าย": "left",
        "ซ้าย": "left",
        "ตรงกลาง": "center",
        "กึ่งกลาง": "center",
        # English
        "right corner": "right",
        "left corner": "left",
        "right side": "right",
        "left side": "left",
        "right end": "right",
        "left end": "left",
    }

    # "head/headboard points/faces toward X" patterns — direction is a facing, not a wall
    _HEAD_TOWARD_PATTERNS = (
        # Thai
        "หันหัว",
        "หันหน้า",
        "หัวเตียง",
        "หัวหมอน",
        "หัวนอน",
        "นอนหัน",
        "วางหัว",
        # English
        "head toward",
        "head facing",
        "headboard toward",
        "headboard facing",
        "sleep facing",
        "facing",
    )

    # "place/move against X wall" patterns — direction is a wall position
    _AGAINST_WALL_PATTERNS = (
        # Thai
        "ชิดกำแพง",
        "ติดกำแพง",
        "ชิดผนัง",
        "ติดผนัง",
        "ย้ายไปที่",
        "ย้ายไปทาง",
        "ไปที่กำแพง",
        # English
        "against",
        "move to",
        "push to",
        "place at",
    )

    # Corner alignment: primary wall + secondary wall → alignment along primary wall.
    # Coordinate system (SpatialResolver): origin = SW corner, z increases NORTH.
    # For east/west walls the alignment axis is Z:
    #   "left"  = z=0          = SOUTH end
    #   "right" = z=depth-size = NORTH end
    # For north/south walls the alignment axis is X:
    #   "left"  = x=0          = WEST end
    #   "right" = x=width-size = EAST end
    _CORNER_ALIGNMENT: dict[tuple[str, str], str] = {
        ("north", "west"): "left",
        ("north", "east"): "right",
        ("south", "west"): "left",
        ("south", "east"): "right",
        ("east", "north"): "right",
        ("east", "south"): "left",
        ("west", "north"): "right",
        ("west", "south"): "left",
    }

    # Keywords that reference a door or window → derive wall from room_spec
    _DOOR_KEYWORDS = (
        "ประตู",
        "ทางเข้า",
        "ทางออก",
        "ประตูห้อง",
        "door",
        "entrance",
        "entry",
    )
    # "Block the doorway" keywords → place on OPPOSITE wall, aligned with door centre
    # These must be checked BEFORE _DOOR_KEYWORDS to take priority.
    # Any of these substrings in the hint triggers "place across from door" logic.
    _BLOCK_DOOR_KEYWORDS = (
        "ขวางประตู",
        "ขวางทางประตู",
        "ขวางทางเข้า",
        "ขวางหน้าประตู",
        "ขวางทาง",
        "block door",
        "block the door",
        "block doorway",
        "block entrance",
        "across from door",
        "opposite the door",
    )
    _WINDOW_KEYWORDS = (
        "หน้าต่าง",
        "ช่องแสง",
        "window",
    )

    @classmethod
    def _parse_wall_and_facing(cls, hint: str) -> tuple[str | None, str | None, str | None]:
        """Parse (target_wall, facing, alignment_override) from a modification hint.

        Cases:
        - Single wall  "ชิดกำแพงตะวันออก"                      → (east, None, None)
        - Head only    "หันหัวไปทางตะวันออก"                    → (west, east, None)
        - Wall+facing  "ชิดตะวันตก หันหัวไปตะวันออก"           → (west, east, None)
        - Corner 2dir  "มุมกำแพงตะวันออกและเหนือ"               → (east, None, "left")
        - Corner align "มุมขวาของกำแพงออกและเหนือ" (ขวา+2dirs)  → (east, None, "right")
        """
        lower = hint.lower()

        # --- 1. Explicit alignment keyword (ขวา/ซ้าย) ---
        alignment_override: str | None = None
        for kw, align in cls._ALIGNMENT_KEYWORDS.items():
            if kw in lower:
                alignment_override = align
                break

        # --- 2. Collect direction mentions in order ---
        found: list[tuple[int, str]] = []
        for keyword, dir_name in cls._DIR_KEYWORDS.items():
            idx = lower.find(keyword)
            if idx != -1:
                found.append((idx, dir_name))
        found.sort()
        seen: set[str] = set()
        dirs: list[str] = []
        for _, d in found:
            if d not in seen:
                seen.add(d)
                dirs.append(d)

        if not dirs:
            return None, None, alignment_override

        has_against = any(pat in lower for pat in cls._AGAINST_WALL_PATTERNS)
        has_head = any(pat in lower for pat in cls._HEAD_TOWARD_PATTERNS)

        if len(dirs) >= 2:
            if dirs[0] == "center":
                return "center", None, None

            if has_head:
                # wall + facing: direction after head-pattern keyword = facing
                head_idx = min(
                    (lower.find(pat) for pat in cls._HEAD_TOWARD_PATTERNS if pat in lower),
                    default=len(lower),
                )
                for pos, d in found:
                    if pos > head_idx and d != "center":
                        facing_dir = d
                        wall_dir = next((x for x in dirs if x != d), dirs[0])
                        return wall_dir, facing_dir, alignment_override
                return dirs[0], dirs[1], alignment_override
            else:
                # Two directions, no head pattern → corner placement
                wall_dir = dirs[0]
                sec_dir = dirs[1]
                # If explicit alignment keyword (ขวา/ซ้าย) was found, use it;
                # otherwise derive from the two wall directions.
                if alignment_override is None:
                    alignment_override = cls._CORNER_ALIGNMENT.get((wall_dir, sec_dir))
                return wall_dir, None, alignment_override

        # Single direction
        direction = dirs[0]
        if direction == "center":
            return "center", None, None

        if has_against and has_head:
            return direction, cls._OPPOSITE.get(direction, direction), alignment_override
        if has_against:
            return direction, None, alignment_override
        if has_head:
            return direction, direction, alignment_override

        # Ambiguous single direction → treat as wall position
        return direction, None, alignment_override

    # Feng shui / abstract move keywords (no specific wall implied)
    _FENG_SHUI_KEYWORDS = (
        "ฮ้วงจุ้ย",
        "feng shui",
        "fengshui",
        "หลักฮ้วงจุ้ย",
        "command position",
        "ตำแหน่งผู้บัญชาการ",
        "ตำแหน่งบัญชาการ",
        "ถูกหลัก",
        "ตามหลัก",
        "ที่เหมาะสม",
        "optimal",
    )

    @classmethod
    def _infer_command_wall(cls, room_spec: dict[str, Any]) -> str | None:
        """Derive the feng shui command wall from the primary door direction."""
        doors = room_spec.get("doors") or (room_spec.get("dimensions") or {}).get("doors") or []
        if not doors:
            return None
        door_wall = str(doors[0].get("wall", "")).lower()
        return cls._OPPOSITE.get(door_wall)

    @classmethod
    def _get_door_wall(cls, room_spec: dict[str, Any]) -> str | None:
        """Return the wall that has the primary door."""
        doors = room_spec.get("doors") or (room_spec.get("dimensions") or {}).get("doors") or []
        if not doors:
            return None
        return str(doors[0].get("wall", "")).lower() or None

    @classmethod
    def _get_door_alignment(cls, room_spec: dict[str, Any], room_w: float, room_d: float) -> str:
        """Return left/center/right alignment of primary door along its wall."""
        doors = room_spec.get("doors") or (room_spec.get("dimensions") or {}).get("doors") or []
        if not doors:
            return "center"
        door = doors[0]
        door_wall = str(door.get("wall", "")).lower()
        offset = float(door.get("offset", 0.0))
        door_w = float(door.get("width", 0.9))
        door_center = offset + door_w / 2
        axis_len = room_w if door_wall in ("north", "south") else room_d
        rel = door_center / axis_len if axis_len > 0 else 0.5
        if rel < 0.33:
            return "left"
        if rel > 0.66:
            return "right"
        return "center"

    @classmethod
    def _get_window_wall(cls, room_spec: dict[str, Any]) -> str | None:
        """Return the wall that has the primary window."""
        windows = (
            room_spec.get("windows") or (room_spec.get("dimensions") or {}).get("windows") or []
        )
        if not windows:
            return None
        return str(windows[0].get("wall", "")).lower() or None

    def _layout_to_semantics(
        self,
        layout: list[dict[str, Any]],
        room_w: float,
        room_d: float,
        target_type: str,
        modification_hint: str,
        room_spec: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Convert physical placement dicts to semantic dicts.

        For the target item, override target_wall and/or facing based on the
        modification hint so LayoutResolver repositions and reorients it correctly.
        """
        target_wall_override, facing_override, alignment_override = self._parse_wall_and_facing(
            modification_hint
        )

        lower_hint = modification_hint.lower()

        logger.info(
            f"ModifierAgent._layout_to_semantics: hint={modification_hint!r} "
            f"parsed: wall={target_wall_override!r} facing={facing_override!r} "
            f"align={alignment_override!r}"
        )
        _doors_debug = room_spec.get("doors") if room_spec else "NO_SPEC"
        logger.info(f"ModifierAgent: room_spec doors={_doors_debug!r}")

        # Fallback: door/window reference → derive wall from room_spec
        if target_wall_override is None and room_spec:
            if any(kw in lower_hint for kw in self._BLOCK_DOOR_KEYWORDS):
                # "ขวางประตู" → place on OPPOSITE wall, aligned with door centre
                door_wall = self._get_door_wall(room_spec)
                if door_wall:
                    target_wall_override = self._OPPOSITE.get(door_wall, door_wall)
                    if alignment_override is None:
                        alignment_override = self._get_door_alignment(room_spec, room_w, room_d)
                    logger.info(
                        f"ModifierAgent: block-door — opposite wall={target_wall_override!r} "
                        f"alignment={alignment_override!r}"
                    )
            elif any(kw in lower_hint for kw in self._DOOR_KEYWORDS):
                door_wall = self._get_door_wall(room_spec)
                if door_wall:
                    target_wall_override = door_wall
                    if alignment_override is None:
                        alignment_override = self._get_door_alignment(room_spec, room_w, room_d)
                    logger.info(
                        f"ModifierAgent: door reference — wall={target_wall_override!r} "
                        f"alignment={alignment_override!r}"
                    )
            elif any(kw in lower_hint for kw in self._WINDOW_KEYWORDS):
                win_wall = self._get_window_wall(room_spec)
                if win_wall:
                    target_wall_override = win_wall
                    logger.info(f"ModifierAgent: window reference — wall={target_wall_override!r}")

        # Fallback: abstract feng shui request → infer command wall from doors
        if target_wall_override is None and room_spec:
            if any(kw in lower_hint for kw in self._FENG_SHUI_KEYWORDS):
                target_wall_override = self._infer_command_wall(room_spec)
                logger.info(
                    f"ModifierAgent: abstract feng shui request — inferred command wall "
                    f"{target_wall_override!r} from doors"
                )

        logger.info(
            f"ModifierAgent: parsed wall={target_wall_override!r} "
            f"facing={facing_override!r} alignment={alignment_override!r} "
            f"from hint {modification_hint!r}"
        )

        result = []
        for i, item in enumerate(layout):
            fw = item.get("dimensions", {}).get("width", 1.0)
            fd = item.get("dimensions", {}).get("depth", 1.0)
            # current_layout pos_x/pos_z are centre-based (room-centre origin).
            # _convert_xyz_to_semantic expects corner-based (SW origin, x=0 = west wall).
            # Conversion: corner = centre + room_half  (furniture left/bottom edge)
            corner_x = item.get("pos_x", 0.0) + room_w / 2
            corner_z = item.get("pos_z", 0.0) + room_d / 2
            semantic = self._llm_agent._convert_xyz_to_semantic(
                {
                    "furniture_id": item.get("furniture_id", item.get("id", f"item_{i}")),
                    "pos_x": corner_x,
                    "pos_z": corner_z,
                    "width": fw,
                    "depth": fd,
                    "height": item.get("dimensions", {}).get("height", 1.0),
                    "priority": i + 1,
                },
                room_w,
                room_d,
            )
            category = item.get("category", "").lower()
            fid = semantic.get("furniture_id", "").lower()
            # Use word-boundary match to avoid "bed" matching "sofa-bed" or "bedside".
            # Split fid/category on non-alphanumeric chars and check exact token match.
            _fid_tokens = set(re.split(r"[-_\s]+", fid))
            _cat_tokens = set(re.split(r"[-_\s]+", category))
            is_target = bool(target_type) and (
                target_type in _fid_tokens or target_type in _cat_tokens
            )
            # Exclude compound furniture whose NAME starts with a different category
            # e.g. "sofa-bed" category="sofa-bed" → primary category is "sofa", not "bed"
            if is_target and fid and not fid.startswith(target_type):
                primary = re.split(r"[-_\s]+", fid)[0]
                if primary and primary != target_type:
                    is_target = False
                    logger.info(
                        f"ModifierAgent: excluding {fid!r} — primary={primary!r} != target={target_type!r}"
                    )
            logger.info(
                f"ModifierAgent: item fid={fid!r} category={category!r} "
                f"target_type={target_type!r} is_target={is_target}"
            )
            if is_target:
                semantic = dict(semantic)
                semantic["orientation"] = modification_hint
                if target_wall_override:
                    semantic["target_wall"] = target_wall_override
                if facing_override:
                    semantic["facing"] = facing_override
                if alignment_override:
                    semantic["alignment"] = alignment_override
                # Place the target first so other items bump around it.
                semantic["priority"] = 0
                logger.info(
                    f"ModifierAgent: overriding target → wall={semantic.get('target_wall')!r} "
                    f"facing={semantic.get('facing')!r} align={semantic.get('alignment')!r}"
                )
            result.append(semantic)
        return result

    @staticmethod
    def _nudge_repair(
        physical: list[dict[str, Any]],
        collisions: list[dict[str, Any]],
        room_w: float,
        room_d: float,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Nudge non-target items away from the target (priority=0) to resolve collisions.

        The target item (priority=0) holds its position; colliding neighbours
        are shifted along X then Z until they no longer overlap.
        """
        # The moved target has priority=0; never nudge it — nudge bystanders instead.
        target_ids: set[str] = {
            item.get("furniture_id", item.get("id", ""))
            for item in physical
            if item.get("priority", 99) == 0
        }

        # Build set of non-target ids involved in any collision
        to_nudge: set[str] = set()
        for c in collisions:
            for fid in c.get("furniture_ids", []):
                if fid not in target_ids:
                    to_nudge.add(fid)
        # Fallback: if all colliding ids are target, nudge all
        if not to_nudge:
            for c in collisions:
                for fid in c.get("furniture_ids", []):
                    to_nudge.add(fid)

        half_w = room_w / 2
        half_d = room_d / 2

        updated = []
        for item in physical:
            fid = item.get("furniture_id", item.get("id", ""))
            if fid in to_nudge:
                item = dict(item)
                w = item.get("dimensions", {}).get("width", 1.0)
                d = item.get("dimensions", {}).get("depth", 1.0)
                # Try nudging along X first, then Z
                new_x = min(item.get("pos_x", 0.0) + _NUDGE_DISTANCE, half_w - w / 2 - 0.05)
                new_x = max(-half_w + w / 2 + 0.05, new_x)
                item["pos_x"] = round(new_x, 3)
                # Also clamp Z within room
                cur_z = item.get("pos_z", 0.0)
                item["pos_z"] = round(
                    max(-half_d + d / 2 + 0.05, min(cur_z, half_d - d / 2 - 0.05)), 3
                )
            updated.append(item)

        # Re-check collisions (centre-based AABB overlap)
        from src.modules.layout.infrastructure.geometry.collision import AABB  # noqa: PLC0415

        remaining: list[dict[str, Any]] = []
        for c in collisions:
            ids = c.get("furniture_ids", [])
            if len(ids) >= 2:
                a = next((i for i in updated if i.get("furniture_id") == ids[0]), None)
                b = next((i for i in updated if i.get("furniture_id") == ids[1]), None)
                if a and b:
                    aw = a.get("dimensions", {}).get("width", 1.0)
                    ad = a.get("dimensions", {}).get("depth", 1.0)
                    bw = b.get("dimensions", {}).get("width", 1.0)
                    bd = b.get("dimensions", {}).get("depth", 1.0)
                    box_a = AABB.from_center_and_size(a.get("pos_x", 0), a.get("pos_z", 0), aw, ad)
                    box_b = AABB.from_center_and_size(b.get("pos_x", 0), b.get("pos_z", 0), bw, bd)
                    if box_a.intersects(box_b):
                        remaining.append(c)

        return updated, remaining

    @staticmethod
    def _enrich_from_current(
        physical: list[dict[str, Any]],
        current_layout: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Copy name/category/is_essential/dimensions from current_layout into new physical items."""
        catalog: dict[str, dict[str, Any]] = {
            item.get("furniture_id", item.get("id", "")): item for item in current_layout
        }
        result = []
        for item in physical:
            fid = item.get("furniture_id", item.get("id", ""))
            src = catalog.get(fid, {})
            enriched: dict[str, Any] = {
                **item,
                "name": src.get("name", item.get("name", fid)),
                "category": src.get("category", item.get("category", fid.split("_")[0])),
                "is_essential": src.get("is_essential", item.get("is_essential", True)),
                "dimensions": item.get("dimensions")
                or src.get("dimensions", {"width": 1.0, "depth": 1.0, "height": 1.0}),
                "feng_shui_notes": src.get("feng_shui_notes", ""),
            }
            # Preserve model_url (3D texture) from current_layout
            model_url = src.get("model_url") or item.get("model_url")
            if model_url:
                enriched["model_url"] = model_url
            result.append(enriched)
        return result
