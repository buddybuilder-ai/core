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
from src.modules.layout.infrastructure.geometry.path_finding import (
    PathFinder,
    PathPoint,
    PathResult,
    PathType,
    TrafficPath,
    calculate_path_efficiency,
    find_direct_line_path,
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
    # Path Finding
    "PathFinder",
    "PathPoint",
    "PathResult",
    "PathType",
    "TrafficPath",
    "calculate_path_efficiency",
    "find_direct_line_path",
]
