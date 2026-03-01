"""Integration layer: LLM semantic placements → physical layout + quality checks.

Converts the LLM's semantic output (wall/alignment intent) to exact coordinates
using SpatialResolver, then runs collision and feng shui checks, and computes
a deterministic score (0-70) that feeds the hybrid scoring pipeline.

No LLM calls. All measurements in meters.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, field_validator

from src.modules.layout.application.services.collision_checker import (
    Collision,
    check_collisions,
)
from src.modules.layout.application.services.feng_shui_checker import (
    FengShuiViolation,
    check_feng_shui,
)
from src.modules.layout.application.services.spatial_resolver import (
    FurnitureSize,
    PhysicalPlacement,
    RoomSpec,
    SemanticPlacement,
    SpatialResolver,
)
from src.modules.layout.domain.entities.room import (
    DoorPosition,
    WallSide,
    WindowPosition,
)

logger = logging.getLogger(__name__)

_VALID_WALLS = {"north", "south", "east", "west", "center"}
_VALID_ALIGNMENTS = {"left", "center", "right"}


# ---------------------------------------------------------------------------
# Pydantic input / output schemas
# ---------------------------------------------------------------------------


class SemanticPlacementSchema(BaseModel):
    """Pydantic schema for validating one LLM semantic placement item."""

    furniture_id: str
    furniture_type: str
    size: dict[str, float]  # {"w": float, "l": float, "h": float}
    target_wall: str
    alignment: str
    offset_from_wall: float
    priority: int
    orientation: str = ""

    @field_validator("target_wall")
    @classmethod
    def valid_wall(cls, v: str) -> str:
        v = v.lower().strip()
        if v not in _VALID_WALLS:
            msg = f"target_wall must be one of {_VALID_WALLS}, got {v!r}"
            raise ValueError(msg)
        return v

    @field_validator("alignment")
    @classmethod
    def valid_alignment(cls, v: str) -> str:
        v = v.lower().strip()
        if v not in _VALID_ALIGNMENTS:
            msg = f"alignment must be one of {_VALID_ALIGNMENTS}, got {v!r}"
            raise ValueError(msg)
        return v


class LayoutResolutionResult(BaseModel):
    """Result of resolving semantic placements into a validated physical layout."""

    physical_placements: list[dict[str, Any]]
    collisions: list[dict[str, Any]]
    feng_shui_violations: list[dict[str, Any]]
    deterministic_score: int  # 0-70  (collision 30 + feng shui 40)


# ---------------------------------------------------------------------------
# LayoutResolver
# ---------------------------------------------------------------------------


class LayoutResolver:
    """Converts LLM semantic placement dicts to a physical layout + quality scores.

    Usage:
        resolver = LayoutResolver()
        result = resolver.resolve(semantic_dicts, room_spec_dict)
        # result.physical_placements → list of placement dicts for the pipeline
        # result.deterministic_score  → 0-70 for hybrid scoring
    """

    def __init__(self) -> None:
        self._spatial = SpatialResolver()

    def resolve(
        self,
        semantic_dicts: list[dict[str, Any]],
        room_spec_dict: dict[str, Any],
    ) -> LayoutResolutionResult:
        """Validate, resolve, and check a list of semantic placements.

        Args:
            semantic_dicts: Raw dicts from LLM (already validated by caller, or
                            will be validated / skipped here with a warning).
            room_spec_dict: Room spec with keys:
                width, depth, doors (list of door dicts), windows (list of
                window dicts).  Door/window dicts use the same shape as
                DoorPosition / WindowPosition fields.

        Returns:
            LayoutResolutionResult with physical placements and scores.
        """
        room = self._build_room_spec(room_spec_dict)

        # Validate each semantic dict; skip invalid ones with a warning
        semantics: list[SemanticPlacement] = []
        for raw in semantic_dicts:
            try:
                schema = SemanticPlacementSchema.model_validate(raw)
                semantics.append(self._schema_to_semantic(schema))
            except Exception as exc:
                fid = raw.get("furniture_id", "<unknown>")
                logger.warning(f"Skipping invalid semantic placement {fid!r}: {exc}")

        if not semantics:
            logger.warning("No valid semantic placements after validation.")
            return LayoutResolutionResult(
                physical_placements=[],
                collisions=[],
                feng_shui_violations=[],
                deterministic_score=0,
            )

        physicals = self._spatial.resolve(semantics, room)
        collisions = check_collisions(physicals, room)
        violations = check_feng_shui(physicals, room)

        det_score = self._score_collisions(collisions) + self._score_feng_shui(violations)

        return LayoutResolutionResult(
            physical_placements=[self._physical_to_dict(p) for p in physicals],
            collisions=[self._collision_to_dict(c) for c in collisions],
            feng_shui_violations=[self._violation_to_dict(v) for v in violations],
            deterministic_score=det_score,
        )

    # ------------------------------------------------------------------
    # Scoring helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _score_collisions(collisions: list[Collision]) -> int:
        """30 points deducting 15 per critical collision and 8 per major."""
        score = 30
        for c in collisions:
            if c.severity == "critical":
                score -= 15
            elif c.severity == "major":
                score -= 8
        return max(0, score)

    @staticmethod
    def _score_feng_shui(violations: list[FengShuiViolation]) -> int:
        """40 points deducting per failed rule: 15 critical, 8 major, 3 minor."""
        score = 40
        for v in violations:
            if not v.passed:
                if v.severity == "critical":
                    score -= 15
                elif v.severity == "major":
                    score -= 8
                else:
                    score -= 3
        return max(0, score)

    # ------------------------------------------------------------------
    # Conversion helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_room_spec(spec: dict[str, Any]) -> RoomSpec:
        doors = [
            DoorPosition(
                wall=WallSide(d["wall"]),
                offset=float(d["offset"]),
                width=float(d.get("width", 0.9)),
            )
            for d in spec.get("doors", [])
        ]
        windows = [
            WindowPosition(
                wall=WallSide(w["wall"]),
                offset=float(w["offset"]),
                width=float(w["width"]),
            )
            for w in spec.get("windows", [])
        ]
        return RoomSpec(
            width=float(spec["width"]),
            depth=float(spec["depth"]),
            doors=doors,
            windows=windows,
        )

    @staticmethod
    def _schema_to_semantic(s: SemanticPlacementSchema) -> SemanticPlacement:
        return SemanticPlacement(
            furniture_id=s.furniture_id,
            furniture_type=s.furniture_type,
            size=FurnitureSize(
                w=float(s.size.get("w", 1.0)),
                l=float(s.size.get("l", 1.0)),
                h=float(s.size.get("h", 1.0)),
            ),
            target_wall=s.target_wall,
            alignment=s.alignment,
            offset_from_wall=s.offset_from_wall,
            priority=s.priority,
            orientation=s.orientation,
        )

    @staticmethod
    def _physical_to_dict(p: PhysicalPlacement) -> dict[str, Any]:
        """Convert PhysicalPlacement to the dict format expected by PipelineState."""
        return {
            "id": p.furniture_id,
            "furniture_id": p.furniture_id,
            # Derive name / category from furniture_id prefix (e.g. "bed_01" → "bed")
            "name": p.furniture_id,
            "category": p.furniture_id.split("_")[0],
            "pos_x": round(p.x, 3),
            "pos_y": 0,
            "pos_z": round(p.z, 3),
            "rotation": p.rotation,
            "dimensions": {
                "width": round(p.bbox.width, 3),
                "depth": round(p.bbox.depth, 3),
                "height": 1.0,  # height not tracked by spatial resolver
            },
            "is_essential": True,
            "feng_shui_notes": "",
        }

    @staticmethod
    def _collision_to_dict(c: Collision) -> dict[str, Any]:
        return {
            "type": c.type,
            "severity": c.severity,
            "furniture_ids": list(c.furniture_ids),
            "description": c.description,
        }

    @staticmethod
    def _violation_to_dict(v: FengShuiViolation) -> dict[str, Any]:
        return {
            "rule_id": v.rule_id,
            "passed": v.passed,
            "severity": v.severity,
            "suggestion": v.suggestion,
        }
