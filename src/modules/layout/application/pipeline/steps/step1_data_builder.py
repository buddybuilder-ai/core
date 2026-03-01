"""Step 1: Structured Data Builder.

Parses raw user input (room dimensions, type, doors, windows, preferences)
into a validated structured RoomSpec. Uses existing InputAnalyzer service.
"""

from __future__ import annotations

import logging
from typing import Any, AsyncGenerator

from src.modules.layout.application.pipeline.models import (
    PipelineConfig,
    PipelineState,
    PipelineStep,
    SSEEvent,
)
from src.modules.layout.application.pipeline.steps.base import BaseStep
from src.modules.layout.application.services import InputAnalyzer, SpatialAnalyzer
from src.modules.layout.domain.entities import DoorPosition, Room, RoomType, WindowPosition

logger = logging.getLogger(__name__)

ROOM_TYPE_MAP = {
    "bedroom": RoomType.BEDROOM,
    "living_room": RoomType.LIVING_ROOM,
    "office": RoomType.OFFICE,
    "dining_room": RoomType.DINING_ROOM,
    "kitchen": RoomType.BEDROOM,
    "bathroom": RoomType.BEDROOM,
    "studio_apartment": RoomType.LIVING_ROOM,
}


class StructuredDataBuilderStep(BaseStep):
    """Step 1: Parse and validate user input into structured RoomSpec."""

    step = PipelineStep.STRUCTURED_DATA_BUILDER

    def __init__(self, config: PipelineConfig) -> None:
        super().__init__(config)
        self._input_analyzer = InputAnalyzer()
        self._spatial_analyzer = SpatialAnalyzer()

    async def execute(
        self, state: PipelineState
    ) -> AsyncGenerator[SSEEvent, None]:
        yield self._emit_started()
        yield self._emit_progress("Parsing room configuration...", 0.2)

        raw = state.room_spec
        if not raw:
            raise ValueError("No room specification provided")

        logger.info(f"📋 STEP 1: Parsing and validating room specification")
        logger.info(f"   Room type: {raw.get('room_type', 'bedroom')}")
        logger.info(f"   Dimensions: {raw.get('width', 0)}m × {raw.get('depth', 0)}m")
        logger.info(f"   Doors: {len(raw.get('doors', []))}, Windows: {len(raw.get('windows', []))}")

        # Validate input
        input_data = self._build_input_data(raw)
        analysis = self._input_analyzer.analyze(input_data)

        if analysis.has_errors:
            error_msg = "; ".join(analysis.error_messages)
            logger.error(f"   ✗ Validation failed: {error_msg}")
            raise ValueError(f"Invalid input: {error_msg}")

        logger.info(f"   ✓ Input validation passed")

        yield self._emit_progress("Building room model...", 0.5)

        # Build Room entity
        room_type_str = raw.get("room_type", "bedroom")
        room_type = ROOM_TYPE_MAP.get(room_type_str, RoomType.BEDROOM)
        logger.info(f"   Building Room entity (type={room_type.value})...")
        dims = raw.get("dimensions", {})

        doors = self._parse_doors(raw.get("doors", []))
        windows = self._parse_windows(raw.get("windows", []))

        room = Room(
            width=dims.get("width", raw.get("width", 4.0)),
            depth=dims.get("depth", raw.get("depth", 3.0)),
            height=dims.get("height", raw.get("height", 2.8)),
            room_type=room_type,
            doors=doors,
            windows=windows,
        )

        yield self._emit_progress("Analyzing spatial characteristics...", 0.7)

        # Spatial analysis
        spatial = self._spatial_analyzer.analyze(room)

        # Store structured data back into state
        state.room_spec = {
            "room_type": room_type_str,
            "width": room.width,
            "depth": room.depth,
            "height": room.height,
            "doors": [self._door_to_dict(d) for d in doors],
            "windows": [self._window_to_dict(w) for w in windows],
            "direction": raw.get("direction", "north"),
            "budget_level": raw.get("budget_level", "medium"),
            "style": raw.get("style"),
            "user_preferences": raw.get("user_preferences", {}),
            # Computed
            "room_area": spatial.room_area,
            "usable_area": spatial.usable_area,
            "command_positions": [p.to_dict() for p in spatial.command_positions],
            "spatial_analysis": spatial.to_dict(),
            # Keep room entity reference
            "_room": room,
            "_spatial": spatial,
        }

        yield self._emit_progress("Room specification complete", 1.0)
        yield self._emit_completed({
            "room_type": room_type_str,
            "dimensions": f"{room.width}m × {room.depth}m",
            "usable_area": f"{spatial.usable_area:.1f} sqm",
            "warnings": analysis.warning_messages,
        })

    def _build_input_data(self, raw: dict[str, Any]) -> dict[str, Any]:
        dims = raw.get("dimensions", {})
        return {
            "room_type": raw.get("room_type", "bedroom"),
            "dimensions": {
                "width": dims.get("width", raw.get("width", 4.0)),
                "depth": dims.get("depth", raw.get("depth", 3.0)),
                "height": dims.get("height", raw.get("height", 2.8)),
            },
            "doors": raw.get("doors", []),
            "windows": raw.get("windows", []),
            "preferences": {
                "budget_level": raw.get("budget_level", "medium"),
            },
        }

    def _parse_doors(self, doors_raw: list[dict]) -> list[DoorPosition]:
        result = []
        for d in doors_raw:
            result.append(DoorPosition(
                wall=d.get("wall", "south"),
                offset=d.get("offset", 1.0),
                width=d.get("width", 0.9),
            ))
        return result

    def _parse_windows(self, windows_raw: list[dict]) -> list[WindowPosition]:
        result = []
        for w in windows_raw:
            result.append(WindowPosition(
                wall=w.get("wall", "north"),
                offset=w.get("offset", 1.0),
                width=w.get("width", 1.5),
            ))
        return result

    def _door_to_dict(self, door: DoorPosition) -> dict[str, Any]:
        return {
            "wall": door.wall,
            "offset": door.offset,
            "width": door.width,
        }

    def _window_to_dict(self, window: WindowPosition) -> dict[str, Any]:
        return {
            "wall": window.wall,
            "offset": window.offset,
            "width": window.width,
        }
