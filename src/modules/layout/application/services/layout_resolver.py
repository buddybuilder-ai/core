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
    facing: str = ""
    along_wall_z: float | None = None  # exact position along wall axis (set by WallAssigner for nightstands)

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
        # Wall assignments are now handled by WallAssigner in langchain_agent
        # so we only validate schema here, no more wall overrides.
        schemas: list[SemanticPlacementSchema] = []
        for raw in semantic_dicts:
            try:
                # Derive furniture_type from furniture_id if missing or looks like a raw ID
                fid = raw.get("furniture_id", "")
                fid_lower = fid.lower()
                current_ftype = raw.get("furniture_type", "")
                import re as _re

                _COMPOUND = {
                    ("sofa", "bed"): "sofa_bed",
                    ("tv", "stand"): "tv_stand",
                    ("coffee", "table"): "coffee_table",
                    ("office", "chair"): "office_chair",
                    ("dining", "chair"): "dining_chair",
                    ("dining", "table"): "dining_table",
                    ("shoe", "cabinet"): "shoe_cabinet",
                    ("coat", "rack"): "coat_rack",
                    ("room", "divider"): "room_divider",
                    ("compact", "wardrobe"): "compact_wardrobe",
                    ("folding", "desk"): "folding_desk",
                    ("area", "rug"): "area_rug",
                    ("floor", "lamp"): "floor_lamp",
                    ("mini", "fridge"): "mini_fridge",
                }
                _COMPOUND_PREFIXES = {k[0] for k in _COMPOUND}
                # Always try compound type from ID tokens first
                if fid:
                    _id_tokens = _re.split(r"[-_\s]+", fid_lower)
                    _derived_compound = None
                    if len(_id_tokens) >= 2 and (_id_tokens[0], _id_tokens[1]) in _COMPOUND:
                        _derived_compound = _COMPOUND[(_id_tokens[0], _id_tokens[1])]
                    if _derived_compound and _derived_compound != current_ftype.lower().replace(
                        "-", "_"
                    ):
                        raw = {**raw, "furniture_type": _derived_compound}
                        logger.info(
                            f"LayoutResolver: derived furniture_type={_derived_compound!r} from id={fid!r} (was {current_ftype!r})"
                        )
                        current_ftype = _derived_compound
                # Detect bad type: empty, contains digits, equals full ID,
                # or is a single-token prefix of a known compound type
                _ftype_norm = current_ftype.lower().replace("-", "_").replace(" ", "_")
                _needs_derive = (
                    not current_ftype
                    or any(c.isdigit() for c in current_ftype)
                    or current_ftype == fid
                    or ("_" not in _ftype_norm and _ftype_norm in _COMPOUND_PREFIXES)
                )
                if _needs_derive and fid:
                    _id_tokens = _re.split(r"[-_\s]+", fid_lower)
                    derived = _id_tokens[0] if _id_tokens else ""
                    if len(_id_tokens) >= 2 and (_id_tokens[0], _id_tokens[1]) in _COMPOUND:
                        derived = _COMPOUND[(_id_tokens[0], _id_tokens[1])]
                    if derived:
                        raw = {**raw, "furniture_type": derived}
                        logger.info(
                            f"LayoutResolver: derived furniture_type={derived!r} from id={fid!r} (was {current_ftype!r})"
                        )
                # ID-based type correction: sofa-bed IDs must be typed as sofa-bed, not bed
                if "sofa-bed" in fid_lower or "sofa_bed" in fid_lower:
                    current_type = raw.get("furniture_type", "")
                    if current_type.lower().replace("-", "_").replace(" ", "_") not in {"sofa_bed"}:
                        raw = {**raw, "furniture_type": "sofa-bed"}
                        logger.info(
                            f"LayoutResolver: corrected furniture_type to 'sofa-bed' for id={fid!r} (was {current_type!r})"
                        )
                # Fill defaults for fields that may be missing
                raw.setdefault("target_wall", "center")
                raw.setdefault("alignment", "center")
                raw.setdefault("offset_from_wall", 0.05)
                logger.info(f"LayoutResolver: validating raw={raw!r}")
                schema = SemanticPlacementSchema.model_validate(raw)
                logger.info(
                    f"LayoutResolver: validated → wall={schema.target_wall!r} align={schema.alignment!r} facing={schema.facing!r}"
                )
                schemas.append(schema)
            except Exception as exc:
                fid = raw.get("furniture_id", "<unknown>")
                logger.warning(f"Skipping invalid semantic placement {fid!r}: {exc}")

        semantics: list[SemanticPlacement] = [self._schema_to_semantic(s) for s in schemas]

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
            physical_placements=[self._physical_to_dict(p, room) for p in physicals],
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
        # Support both flat {"width": x, "depth": y} and nested {"dimensions": {"width": x, "depth": y}}
        dims = spec.get("dimensions") or {}
        width = float(spec.get("width") or dims.get("width") or 0)
        depth = float(spec.get("depth") or dims.get("depth") or 0)
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
            width=width,
            depth=depth,
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
                length=float(s.size.get("l", 1.0)),
                h=float(s.size.get("h", 1.0)),
            ),
            target_wall=s.target_wall,
            alignment=s.alignment,
            offset_from_wall=s.offset_from_wall,
            priority=s.priority,
            orientation=s.orientation,
            facing=s.facing,
            along_wall_z=s.along_wall_z,
        )

    @staticmethod
    def _physical_to_dict(p: PhysicalPlacement, room: RoomSpec) -> dict[str, Any]:
        """Convert PhysicalPlacement to the dict format expected by PipelineState.

        Backend uses SW-corner origin (0,0) with pos_x/pos_z as the left/top
        edge of the furniture footprint.  The frontend Three.js scene uses the
        room centre as origin and expects pos_x/pos_z to be the *centre* of the
        furniture.

        IMPORTANT: The frontend BoxGeometry uses pre-rotation dimensions.
        Rotation is applied by the Three.js group, so we must send the
        *post-rotation footprint* dimensions so the box matches the physical
        footprint after the group rotation is applied.  In practice:
          - rotation 0°/180°: bbox.width → box width, bbox.depth → box depth
          - rotation 90°/270°: bbox.width is the Z-dimension of the original,
            bbox.depth is the X-dimension.  We keep bbox sizes as sent
            dimensions so the rendered box matches the physical footprint.

        Conversion (corner → centre, room-centre origin):
            frontend_centre_x = backend_left_x + footprint_w/2 - room_width/2
            frontend_centre_z = -(backend_top_z + footprint_d/2 - room_depth/2)

        NOTE: Z must be negated because backend uses z=0 at south wall, z increases
        north; but Three.js scene uses z=0 at room centre, z=-halfD at north wall,
        z=+halfD at south wall (i.e. z increases south, opposite of backend).
        """
        fw = round(p.bbox.width, 3)  # x-size of footprint in room (post-rotation)
        fd = round(p.bbox.depth, 3)  # z-size of footprint in room (post-rotation)
        centre_x = round(p.x + fw / 2 - room.width / 2, 3)
        centre_z = round(-(p.z + fd / 2 - room.depth / 2), 3)

        # Send dimensions as footprint sizes (post-rotation).
        # The Three.js group is already rotated, so we must pass the rotated
        # box sizes.  For rotations 90/270 the width↔depth are swapped
        # compared to the "natural" furniture orientation, but since the group
        # rotation accounts for that visually, passing footprint sizes gives
        # the correct physical extents.
        rot = p.rotation % 360
        if rot in (90, 270):
            # Swap back so Three.js BoxGeometry(w, h, d) + rotation gives right shape
            dim_w = fd  # original depth becomes box width
            dim_d = fw  # original width becomes box depth
        else:
            dim_w = fw
            dim_d = fd

        # Derive which wall the furniture is against from actual position.
        # Compute distance to each wall edge, then pick the closest one that
        # is within tolerance. This handles corner items correctly (e.g. a
        # wardrobe at x=6.4,z=0 in a 7x4 room is against the east wall, not south).
        _WALL_TOL = 0.35
        dist_south = p.z
        dist_north = room.depth - (p.z + fd)
        dist_west = p.x
        dist_east = room.width - (p.x + fw)
        candidates = {
            "south": dist_south,
            "north": dist_north,
            "west": dist_west,
            "east": dist_east,
        }
        _ROT_TO_WALL = {0: "north", 180: "south", 90: "west", 270: "east"}
        rot_wall = _ROT_TO_WALL.get(p.rotation % 360, "center")
        within_tol = {w: d for w, d in candidates.items() if d <= _WALL_TOL}
        if within_tol:
            # If rotation wall is among candidates within tolerance, prefer it (tie-break)
            if rot_wall in within_tol:
                wall = rot_wall
            else:
                wall = min(within_tol, key=within_tol.__getitem__)
        else:
            wall = rot_wall

        logger.info(
            f"_physical_to_dict: {p.furniture_id} "
            f"backend=({p.x:.3f},{p.z:.3f}) rot={p.rotation}° "
            f"footprint={fw}x{fd} room=({room.width}x{room.depth}) → "
            f"frontend=({centre_x},{centre_z}) dim={dim_w}x{dim_d} wall={wall}"
        )

        return {
            "id": p.furniture_id,
            "furniture_id": p.furniture_id,
            # Derive name / category from furniture_id prefix (e.g. "bed_01" → "bed")
            "name": p.furniture_id,
            "category": p.furniture_id.split("_")[0],
            "pos_x": centre_x,
            "pos_y": 0,
            "pos_z": centre_z,
            "rotation": p.rotation,
            "wall": wall,
            "dimensions": {
                "width": dim_w,
                "depth": dim_d,
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
