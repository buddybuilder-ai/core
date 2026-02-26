"""Step 2: Layout Generator (Planner).

Generates initial furniture layout using heuristic placement:
- Big items first, wall alignment
- Uses existing FurnitureSelector + PlacementEngine services
"""

from __future__ import annotations

import logging
from typing import AsyncGenerator

from src.modules.layout.application.dtos import (
    AgentContext,
    PlacedFurniture,
    UserPreferences,
)
from src.modules.layout.application.pipeline.models import (
    PipelineConfig,
    PipelineState,
    PipelineStep,
    SSEEvent,
    SSEEventType,
)
from src.modules.layout.application.pipeline.steps.base import BaseStep
from src.modules.layout.application.services import (
    FurnitureSelector,
    PlacementEngine,
)
from src.modules.layout.domain.entities import Room
from src.modules.layout.infrastructure.tools import InMemoryFurnitureDbTool

logger = logging.getLogger(__name__)


class LayoutGeneratorStep(BaseStep):
    """Step 2: Generate initial layout via heuristic placement."""

    step = PipelineStep.LAYOUT_GENERATOR

    def __init__(self, config: PipelineConfig) -> None:
        super().__init__(config)
        self._furniture_tool = InMemoryFurnitureDbTool()
        self._furniture_selector = FurnitureSelector(self._furniture_tool)

    async def execute(
        self, state: PipelineState
    ) -> AsyncGenerator[SSEEvent, None]:
        yield self._emit_started()

        spec = state.room_spec
        room: Room = spec.get("_room")
        spatial = spec.get("_spatial")

        if not room:
            raise ValueError("Room not built — run Step 1 first")

        # --- Select furniture ---
        yield self._emit_progress("Selecting furniture for room...", 0.2)

        preferences = UserPreferences(
            budget_level=spec.get("budget_level", "medium"),
        )
        selection_result = await self._furniture_selector.select_furniture(
            room_type=spec.get("room_type", "bedroom"),
            usable_area=spec.get("usable_area", room.width * room.depth * 0.8),
            preferences=preferences,
            max_items=12,
        )

        selections = selection_result.get_by_priority()
        if not selections:
            raise ValueError("No furniture could be selected for this room")

        yield self._emit_progress(
            f"Selected {len(selections)} items, placing...", 0.4
        )

        # --- Place furniture ---
        engine = PlacementEngine(
            room_width=room.width,
            room_depth=room.depth,
        )
        batch_result = engine.place_all(selections, spatial)

        yield self._emit_progress(
            f"Placed {batch_result.placed_count}/{batch_result.total_items} items",
            0.8,
        )

        if batch_result.placed_count == 0:
            raise ValueError("No furniture could be placed in the room")

        # Convert placed furniture to pipeline format
        placed_items = engine.get_placed_furniture()
        layout_items = [self._furniture_to_dict(f) for f in placed_items]

        state.layout_items = layout_items

        # Emit layout update for progressive rendering
        yield SSEEvent(
            event_type=SSEEventType.LAYOUT_UPDATED,
            data={"items": layout_items, "step": self.step.value},
        )

        yield self._emit_completed({
            "placed_count": batch_result.placed_count,
            "total_selected": batch_result.total_items,
            "skipped_count": batch_result.skipped_count,
            "success_rate": f"{batch_result.success_rate:.0%}",
        })

    def _furniture_to_dict(self, f: PlacedFurniture) -> dict:
        return {
            "id": f.id,
            "furniture_id": f.furniture_id,
            "name": f.name,
            "category": f.category,
            "pos_x": round(f.pos_x, 3),
            "pos_y": 0,
            "pos_z": round(f.pos_z, 3),
            "rotation": f.rotation,
            "dimensions": {
                "width": f.width,
                "depth": f.depth,
                "height": f.height,
            },
            "is_essential": f.is_essential,
            "feng_shui_notes": f.feng_shui_notes,
        }
