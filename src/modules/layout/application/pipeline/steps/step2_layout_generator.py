"""Step 2: Layout Generator (Planner).

Generates the initial furniture layout using the LLM semantic placement flow:
1. FurnitureSelector picks which items to place
2. FengShuiLLMAgent.plan_layout() returns semantic placement intent
3. LayoutResolver resolves semantic → physical + runs collision/feng-shui checks
4. Results stored on PipelineState for Step 3 to score and repair
"""

from __future__ import annotations

import logging
import re
from collections.abc import AsyncGenerator
from typing import Any

from src.modules.layout.application.dtos import UserPreferences
from src.modules.layout.application.pipeline.models import (
    PipelineConfig,
    PipelineState,
    PipelineStep,
    SSEEvent,
    SSEEventType,
)
from src.modules.layout.application.pipeline.steps.base import BaseStep
from src.modules.layout.application.services import FurnitureSelector
# furniture_relationships hints are no longer injected into LLM prompt;
# WallAssigner handles spatial logic deterministically.
from src.modules.layout.application.services.layout_resolver import LayoutResolver
from src.modules.layout.domain.entities import Room
from src.modules.layout.infrastructure.llm.langchain_agent import (
    FengShuiLLMAgent,
    LLMConfig,
)
from src.modules.layout.infrastructure.tools import InMemoryFurnitureDbTool

logger = logging.getLogger(__name__)


class LayoutGeneratorStep(BaseStep):
    """Step 2: Generate initial layout via LLM semantic placement + resolver."""

    step = PipelineStep.LAYOUT_GENERATOR

    def __init__(self, config: PipelineConfig) -> None:
        super().__init__(config)
        self._furniture_tool = InMemoryFurnitureDbTool()
        self._furniture_selector = FurnitureSelector(self._furniture_tool)
        self._llm_agent = FengShuiLLMAgent(LLMConfig())
        self._resolver = LayoutResolver()

    async def execute(self, state: PipelineState) -> AsyncGenerator[SSEEvent, None]:
        yield self._emit_started()

        spec = state.room_spec
        room: Room | None = spec.get("_room")

        if not room:
            raise ValueError("Room not built — run Step 1 first")

        # --- 1. Select furniture ---
        yield self._emit_progress("Selecting furniture for room...", 0.15)

        preferences = UserPreferences(
            budget_level=spec.get("budget_level", "medium"),
        )
        room_type = spec.get("room_type", "bedroom")
        usable_area = spec.get("usable_area", room.width * room.depth * 0.8)

        logger.info(f"🧠 STEP 2: Selecting furniture for {room_type}")
        logger.info(f"   Room: {room.width}m × {room.depth}m, Usable: {usable_area:.1f} sqm")

        # If user specified owned furniture, restrict catalog to only those items
        user_prefs = spec.get("user_preferences") or {}
        user_message = user_prefs.get("user_message", "")
        owned_categories = self._parse_owned_furniture(user_message)
        if owned_categories:
            logger.info(
                f"   🔒 User owns specific furniture: {owned_categories} — restricting catalog"
            )

        selection_result = await self._furniture_selector.select_furniture(
            room_type=room_type,
            usable_area=usable_area,
            preferences=preferences,
            max_items=12,
            owned_categories=owned_categories or None,
        )

        selections = selection_result.get_by_priority()
        if not selections:
            raise ValueError("No furniture could be selected for this room")

        logger.info(f"   ✓ Selected {len(selections)} items")

        yield self._emit_progress(f"Selected {len(selections)} items, planning layout...", 0.3)

        # --- 2. Build furniture list for LLM ---
        furniture_list = [
            {
                "id": sel.item.id,
                "name": sel.item.name,
                "width": sel.item.width,
                "depth": sel.item.depth,
                "height": getattr(sel.item, "height", 1.0),
                "is_essential": getattr(sel.item, "is_essential", True),
            }
            for sel in selections
        ]

        doors = [{"wall": d.wall.value, "offset": d.offset, "width": d.width} for d in room.doors]
        windows = [
            {"wall": w.wall.value, "offset": w.offset, "width": w.width} for w in room.windows
        ]

        command_pos = spec.get("command_positions", [])

        # --- 3. LLM semantic placement ---
        yield self._emit_progress("LLM planning semantic layout...", 0.5)
        logger.info("🤖 Calling LLM for semantic layout plan...")

        extra_ctx = state.rag_context.get("layout_prompt_context", "")
        if extra_ctx:
            logger.info(f"   Injecting {len(extra_ctx)} chars of RAG context into LLM prompt")

        merged_prefs = user_prefs if user_prefs else None

        llm_response = await self._llm_agent.plan_layout(
            room_type=room_type,
            width=room.width,
            depth=room.depth,
            usable_area=usable_area,
            doors=doors,
            windows=windows,
            furniture_list=furniture_list,
            command_positions=command_pos,
            extra_context=extra_ctx,
            user_preferences=merged_prefs if merged_prefs else None,
        )

        if not llm_response.success:
            logger.warning(
                f"LLM plan_layout failed: {llm_response.error}. "
                "Falling back to heuristic placement."
            )
            layout_items = self._heuristic_fallback(selections, room)
            state.layout_items = layout_items
            state.feng_shui_score["deterministic"] = 0
            yield SSEEvent(
                event_type=SSEEventType.LAYOUT_UPDATED,
                data={"items": layout_items, "step": self.step.value},
            )
            yield self._emit_completed(
                {
                    "placed_count": len(layout_items),
                    "source": "heuristic_fallback",
                }
            )
            return

        semantic_placements = llm_response.content.get("placements", [])
        logger.info(f"   ✓ LLM returned {len(semantic_placements)} semantic placements")

        if not semantic_placements:
            raise ValueError("LLM returned no valid semantic placements")

        # Merge LLM furniture_type/size with known catalog dimensions
        semantic_placements = self._enrich_placements(semantic_placements, furniture_list)

        yield self._emit_progress("Resolving positions and checking layout...", 0.75)

        # --- 4. Resolve semantic → physical + checks ---
        room_spec_dict: dict[str, Any] = {
            "width": room.width,
            "depth": room.depth,
            "doors": doors,
            "windows": windows,
        }

        resolution = self._resolver.resolve(semantic_placements, room_spec_dict)

        logger.info(
            f"   ✓ Resolved {len(resolution.physical_placements)} items; "
            f"collisions={len(resolution.collisions)}, "
            f"fs_violations={len(resolution.feng_shui_violations)}, "
            f"det_score={resolution.deterministic_score}/70"
        )

        # Enrich physical placements with catalog metadata
        layout_items = self._enrich_with_catalog(
            resolution.physical_placements, furniture_list, selections
        )

        state.layout_items = layout_items
        state.feng_shui_score["deterministic"] = resolution.deterministic_score

        yield SSEEvent(
            event_type=SSEEventType.LAYOUT_UPDATED,
            data={"items": layout_items, "step": self.step.value},
        )

        yield self._emit_completed(
            {
                "placed_count": len(layout_items),
                "collisions": len(resolution.collisions),
                "feng_shui_violations": len(resolution.feng_shui_violations),
                "deterministic_score": resolution.deterministic_score,
                "source": "llm_semantic",
            }
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _enrich_placements(
        placements: list[dict[str, Any]],
        furniture_list: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Fill in size from the catalog if the LLM omitted it or used wrong dims."""
        catalog_map = {f["id"]: f for f in furniture_list}
        enriched = []
        for p in placements:
            fid = p.get("furniture_id", "")
            catalog_item = catalog_map.get(fid)
            if catalog_item:
                p = dict(p)
                # Always use catalog dims — LLM may have guessed wrong furniture_id
                # (and therefore wrong size). Catalog is the ground truth.
                p["size"] = {
                    "w": catalog_item["width"],
                    "l": catalog_item["depth"],
                    "h": catalog_item.get("height", 1.0),
                }
                if not p.get("furniture_type"):
                    p["furniture_type"] = fid.split("_")[0]
            enriched.append(p)
        return enriched

    @staticmethod
    def _enrich_with_catalog(
        physical: list[dict[str, Any]],
        furniture_list: list[dict[str, Any]],
        selections: list[Any],
    ) -> list[dict[str, Any]]:
        """Add name/category/is_essential from catalog to physical placement dicts."""
        catalog_map = {f["id"]: f for f in furniture_list}
        sel_map = {sel.item.id: sel for sel in selections if hasattr(sel, "item")}
        result = []
        for item in physical:
            fid = item.get("furniture_id", item.get("id", ""))
            cat = catalog_map.get(fid, {})
            sel = sel_map.get(fid)
            dims = item.get("dimensions", {})
            enriched_item: dict[str, Any] = {
                **item,
                "name": cat.get("name", fid),
                "category": cat.get("category", fid.split("_")[0]),
                "is_essential": getattr(getattr(sel, "item", None), "is_essential", True),
                "dimensions": {
                    "width": dims.get("width", cat.get("width", 1.0)),
                    "depth": dims.get("depth", cat.get("depth", 1.0)),
                    "height": dims.get("height", cat.get("height", 1.0)),
                },
                "feng_shui_notes": "",
            }
            # Carry model_rotation_offset from catalog so the frontend knows how
            # to correct for the 3D model's exported "forward" direction.
            mro = cat.get("model_rotation_offset", 0)
            if mro:
                enriched_item["model_rotation_offset"] = int(mro)
            result.append(enriched_item)
        return result

    @staticmethod
    def _parse_owned_furniture(user_message: str) -> list[str]:
        """Extract furniture categories the user explicitly says they own.

        Returns a list of catalog category strings (e.g. ["bed", "desk"]).
        Returns empty list if no ownership cues are found.
        """
        if not user_message:
            return []

        # Keyword → catalog category mapping (Thai + English)
        OWNED_KEYWORDS: list[tuple[str, str]] = [
            # Beds
            (r"เตียง|ที่นอน|bed", "bed"),
            # Desks / tables (computer desk first so it wins over generic "โต๊ะ")
            (r"โต๊ะคอม|โต๊ะทำงาน|computer\s*desk|work\s*desk|desk", "desk"),
            # Wardrobe / closet
            (r"ตู้เสื้อผ้า|ตู้เก็บของ|wardrobe|closet|compact.wardrobe", "compact_wardrobe"),
            # Sofa / couch
            (r"โซฟา|sofa|couch", "sofa"),
            # Sofa-bed
            (r"โซฟาเตียง|sofa.bed", "sofa_bed"),
            # Folding desk
            (r"โต๊ะพับ|folding.desk", "folding_desk"),
            # Chair
            (r"เก้าอี้|chair", "chair"),
            # Bookshelf
            (r"ชั้นหนังสือ|ชั้นวาง|bookshelf|shelf", "bookshelf"),
            # TV stand
            (r"ตู้ทีวี|tv.stand|television", "tv_stand"),
            # Nightstand
            (r"โต๊ะข้างเตียง|nightstand|bedside", "nightstand"),
            # Dresser / drawer
            (r"ลิ้นชัก|dresser|drawer", "dresser"),
            # Compact dining
            (r"โต๊ะกิน|โต๊ะอาหาร|dining|compact.dining", "compact_dining"),
        ]

        # Ownership trigger patterns — only extract if user signals ownership
        OWNERSHIP_CUES = re.compile(
            r"มีแค่|มีเพียง|มีแต่|ของฉัน|ที่มี|own|only have|have only|just have|i have",
            re.IGNORECASE,
        )

        if not OWNERSHIP_CUES.search(user_message):
            return []

        msg_lower = user_message.lower()
        found: list[str] = []
        for pattern, category in OWNED_KEYWORDS:
            if re.search(pattern, msg_lower, re.IGNORECASE) and category not in found:
                found.append(category)

        return found

    def _heuristic_fallback(self, selections: list[Any], room: Room) -> list[dict[str, Any]]:
        """Simple fallback: stack items along the south wall."""
        items = []
        x = 0.05
        for sel in selections:
            item = sel.item
            w = getattr(item, "width", 1.0)
            d = getattr(item, "depth", 1.0)
            h = getattr(item, "height", 1.0)
            if x + w > room.width:
                break
            items.append(
                {
                    "id": item.id,
                    "furniture_id": item.id,
                    "name": item.name,
                    "category": getattr(item.category, "value", str(item.category)),
                    "pos_x": round(x, 3),
                    "pos_y": 0,
                    "pos_z": 0.05,
                    "rotation": 0,
                    "dimensions": {"width": w, "depth": d, "height": h},
                    "is_essential": getattr(item, "is_essential", False),
                    "feng_shui_notes": "",
                }
            )
            x += w + 0.1
        return items
