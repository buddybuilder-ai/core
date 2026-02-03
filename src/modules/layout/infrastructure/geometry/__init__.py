"""Geometry module for feng shui layout generation."""

from src.modules.layout.infrastructure.geometry.collision import (
    AABB,
    ClearanceRequirement,
    CollisionDetector,
    CollisionResult,
    CollisionSeverity,
    check_rotated_collision,
)
from src.modules.layout.infrastructure.geometry.grid import (
    CellState,
    GridPosition,
    GridRect,
    PlacementCandidate,
    PlacementGrid,
)

__all__ = [
    # Collision
    "AABB",
    "ClearanceRequirement",
    "CollisionDetector",
    "CollisionResult",
    "CollisionSeverity",
    "check_rotated_collision",
    # Grid
    "CellState",
    "GridPosition",
    "GridRect",
    "PlacementCandidate",
    "PlacementGrid",
]
