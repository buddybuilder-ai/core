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
from typing import Any, AsyncGenerator

from src.modules.layout.application.pipeline.models import (
    PipelineConfig,
    SSEEvent,
    SSEEventType,
)
from src.modules.layout.application.services.layout_resolver import LayoutResolver
from src.modules.layout.infrastructure.llm.langchain_agent import (
    FengShuiLLMAgent,
    LLMConfig,
)

logger = logging.getLogger(__name__)

# Maximum nudge attempts when collisions remain after modification
_MAX_REPAIR_ATTEMPTS = 3
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

        room_w = float(room_spec.get("width", 4.0))
        room_d = float(room_spec.get("depth", 4.0))
        target_type = str(extracted_params.get("target_furniture", "")).lower()

        # --- 1. Build semantic placements from existing physical layout ---
        yield SSEEvent(
            event_type=SSEEventType.STEP_PROGRESS,
            data={"step": "modifier", "message": "Analysing current layout...", "progress": 0.2},
        )

        semantic_placements = self._layout_to_semantics(
            current_layout, room_w, room_d, target_type, modification_request
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

        # --- 2. Re-plan with LLM ---
        yield SSEEvent(
            event_type=SSEEventType.STEP_PROGRESS,
            data={"step": "modifier", "message": "Planning modified layout...", "progress": 0.45},
        )

        doors = room_spec.get("doors", [])
        windows = room_spec.get("windows", [])

        # Build furniture_list from current layout for the LLM call
        furniture_list = [
            {
                "id": item.get("furniture_id", item.get("id", "")),
                "name": item.get("name", ""),
                "width": item.get("dimensions", {}).get("width", 1.0),
                "depth": item.get("dimensions", {}).get("depth", 1.0),
                "height": item.get("dimensions", {}).get("height", 1.0),
                "is_essential": item.get("is_essential", True),
            }
            for item in current_layout
        ]

        room_type = room_spec.get("room_type", "room")

        llm_response = await self._llm_agent.plan_layout(
            room_type=room_type,
            width=room_w,
            depth=room_d,
            usable_area=room_w * room_d * 0.8,
            doors=doors,
            windows=windows,
            furniture_list=furniture_list,
            command_positions=[],
        )

        if not llm_response.success:
            logger.warning(
                f"ModifierAgent: LLM re-plan failed ({llm_response.error}), "
                "using back-converted semantics as-is"
            )
            new_semantics = semantic_placements
        else:
            new_semantics = llm_response.content.get("placements", semantic_placements)

        yield SSEEvent(
            event_type=SSEEventType.STEP_PROGRESS,
            data={"step": "modifier", "message": "Resolving positions...", "progress": 0.65},
        )

        # --- 3. Resolve semantic → physical ---
        resolution = self._resolver.resolve(new_semantics, room_spec)

        # --- 4. Nudge repair for remaining collisions ---
        collisions = resolution.collisions
        physical = resolution.physical_placements

        for attempt in range(_MAX_REPAIR_ATTEMPTS):
            if not collisions:
                break
            logger.debug(
                f"ModifierAgent: repair attempt {attempt + 1}, "
                f"{len(collisions)} collisions"
            )
            physical, collisions = self._nudge_repair(physical, collisions, room_w, room_d)

        yield SSEEvent(
            event_type=SSEEventType.STEP_PROGRESS,
            data={"step": "modifier", "message": "Finalising...", "progress": 0.9},
        )

        # Enrich physical placements with catalog metadata from current_layout
        enriched = self._enrich_from_current(physical, current_layout)

        yield SSEEvent(
            event_type=SSEEventType.MODIFIER_UPDATED,
            data={"items": enriched},
        )

        yield SSEEvent(
            event_type=SSEEventType.MODIFIER_COMPLETED,
            data={
                "changed_furniture": target_type,
                "placed_count": len(enriched),
                "collisions_after": len(collisions),
                "deterministic_score": resolution.deterministic_score,
            },
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _layout_to_semantics(
        self,
        layout: list[dict[str, Any]],
        room_w: float,
        room_d: float,
        target_type: str,
        modification_hint: str,
    ) -> list[dict[str, Any]]:
        """Convert physical placement dicts to semantic dicts.

        For the target item, the orientation field is overridden with the
        modification hint so the LLM understands the intent.
        """
        result = []
        for i, item in enumerate(layout):
            semantic = self._llm_agent._convert_xyz_to_semantic(
                {
                    "furniture_id": item.get("furniture_id", item.get("id", f"item_{i}")),
                    "pos_x": item.get("pos_x", 0.0),
                    "pos_z": item.get("pos_z", 0.0),
                    "width": item.get("dimensions", {}).get("width", 1.0),
                    "depth": item.get("dimensions", {}).get("depth", 1.0),
                    "height": item.get("dimensions", {}).get("height", 1.0),
                    "priority": i + 1,
                },
                room_w,
                room_d,
            )
            category = item.get("category", "").lower()
            if target_type and (target_type in category or target_type in semantic.get("furniture_id", "").lower()):
                semantic = dict(semantic)
                semantic["orientation"] = modification_hint
            result.append(semantic)
        return result

    @staticmethod
    def _nudge_repair(
        physical: list[dict[str, Any]],
        collisions: list[dict[str, Any]],
        room_w: float,
        room_d: float,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Nudge items involved in collisions by _NUDGE_DISTANCE along x-axis.

        This is a best-effort single-axis shift — the full SpatialResolver
        handles proper placement; this is only a fallback repair.
        """
        colliding_ids: set[str] = set()
        for c in collisions:
            for fid in c.get("furniture_ids", []):
                colliding_ids.add(fid)

        updated = []
        for item in physical:
            fid = item.get("furniture_id", item.get("id", ""))
            if fid in colliding_ids:
                item = dict(item)
                w = item.get("dimensions", {}).get("width", 1.0)
                new_x = min(item.get("pos_x", 0.0) + _NUDGE_DISTANCE, room_w - w - 0.05)
                item["pos_x"] = round(max(0.05, new_x), 3)
            updated.append(item)

        # Re-check collisions naively (overlap on x-axis only)
        remaining: list[dict[str, Any]] = []
        for c in collisions:
            ids = c.get("furniture_ids", [])
            if len(ids) >= 2:
                a = next((i for i in updated if i.get("furniture_id") == ids[0]), None)
                b = next((i for i in updated if i.get("furniture_id") == ids[1]), None)
                if a and b:
                    aw = a.get("dimensions", {}).get("width", 1.0)
                    bw = b.get("dimensions", {}).get("width", 1.0)
                    if abs(a["pos_x"] - b["pos_x"]) < (aw + bw) / 2:
                        remaining.append(c)

        return updated, remaining

    @staticmethod
    def _enrich_from_current(
        physical: list[dict[str, Any]],
        current_layout: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Copy name/category/is_essential/dimensions from current_layout into new physical items."""
        catalog: dict[str, dict[str, Any]] = {
            item.get("furniture_id", item.get("id", "")): item
            for item in current_layout
        }
        result = []
        for item in physical:
            fid = item.get("furniture_id", item.get("id", ""))
            src = catalog.get(fid, {})
            result.append({
                **item,
                "name": src.get("name", item.get("name", fid)),
                "category": src.get("category", item.get("category", fid.split("_")[0])),
                "is_essential": src.get("is_essential", item.get("is_essential", True)),
                "dimensions": item.get("dimensions") or src.get("dimensions", {"width": 1.0, "depth": 1.0, "height": 1.0}),
                "feng_shui_notes": src.get("feng_shui_notes", ""),
            })
        return result
