"""Path finding algorithms for feng shui layout generation."""

from dataclasses import dataclass, field
from enum import StrEnum
from heapq import heappop, heappush
from typing import NamedTuple

from src.modules.layout.infrastructure.geometry.collision import AABB
from src.modules.layout.infrastructure.geometry.grid import (
    CellState,
    GridPosition,
    PlacementGrid,
)


class PathType(StrEnum):
    """Types of paths in a room."""

    TRAFFIC = "traffic"  # Main traffic path through room
    ACCESS = "access"  # Access to furniture
    EMERGENCY = "emergency"  # Emergency exit path
    CHI_FLOW = "chi_flow"  # Feng shui chi energy flow


class PathResult(NamedTuple):
    """Result of a path finding operation.

    Attributes:
        found: Whether a valid path was found.
        path: List of grid positions in the path.
        length: Total path length in meters.
        width: Minimum width along the path.
        message: Human-readable description.
    """

    found: bool
    path: list[GridPosition]
    length: float
    width: float
    message: str


@dataclass(frozen=True)
class PathPoint:
    """A point in world coordinates for path representation.

    Attributes:
        x: X coordinate in meters.
        z: Z coordinate in meters.
    """

    x: float
    z: float

    def distance_to(self, other: "PathPoint") -> float:
        """Calculate distance to another point."""
        return ((self.x - other.x) ** 2 + (self.z - other.z) ** 2) ** 0.5


@dataclass
class TrafficPath:
    """Represents a traffic path through the room.

    Attributes:
        points: List of path waypoints.
        width: Path width in meters.
        path_type: Type of this path.
        is_valid: Whether the path meets minimum requirements.
    """

    points: list[PathPoint]
    width: float
    path_type: PathType
    is_valid: bool = True

    @property
    def length(self) -> float:
        """Calculate total path length."""
        if len(self.points) < 2:
            return 0.0
        total = 0.0
        for i in range(len(self.points) - 1):
            total += self.points[i].distance_to(self.points[i + 1])
        return total

    def get_bounding_boxes(self) -> list[AABB]:
        """Get bounding boxes for the path segments."""
        boxes = []
        half_width = self.width / 2
        for i in range(len(self.points) - 1):
            p1, p2 = self.points[i], self.points[i + 1]
            min_x = min(p1.x, p2.x) - half_width
            max_x = max(p1.x, p2.x) + half_width
            min_z = min(p1.z, p2.z) - half_width
            max_z = max(p1.z, p2.z) + half_width
            boxes.append(AABB(min_x=min_x, min_z=min_z, max_x=max_x, max_z=max_z))
        return boxes


@dataclass
class PathFinder:
    """Path finding for feng shui layout.

    Provides methods for:
    - Finding traffic paths between doors
    - Verifying emergency exit accessibility
    - Calculating chi flow paths
    - Checking furniture accessibility
    """

    room_width: float
    room_depth: float
    cell_size: float = 0.1  # 10cm resolution

    # Minimum path widths
    MIN_TRAFFIC_WIDTH: float = 0.6  # 60cm for traffic
    MIN_EMERGENCY_WIDTH: float = 0.9  # 90cm for emergency
    MIN_ACCESS_WIDTH: float = 0.45  # 45cm for furniture access

    _grid: PlacementGrid = field(init=False)

    def __post_init__(self) -> None:
        """Initialize the path finding grid."""
        if self.room_width <= 0 or self.room_depth <= 0:
            raise ValueError("Room dimensions must be positive")
        self._grid = PlacementGrid(
            width=self.room_width,
            depth=self.room_depth,
            cell_size=self.cell_size,
        )

    def set_obstacles(self, obstacles: list[AABB]) -> None:
        """Set obstacles on the grid.

        Args:
            obstacles: List of furniture/obstacle bounding boxes.
        """
        self._grid.clear()
        for i, obstacle in enumerate(obstacles):
            self._grid.mark_occupied(
                item_id=f"obstacle_{i}",
                x=obstacle.min_x,
                z=obstacle.min_z,
                width=obstacle.width,
                depth=obstacle.depth,
            )

    def find_path(
        self,
        start: PathPoint,
        end: PathPoint,
        min_width: float | None = None,
    ) -> PathResult:
        """Find a path between two points using A* algorithm.

        Args:
            start: Starting point.
            end: Ending point.
            min_width: Minimum path width required.

        Returns:
            PathResult with path details.
        """
        if min_width is None:
            min_width = self.MIN_TRAFFIC_WIDTH

        # Convert to grid positions
        start_pos = GridPosition.from_world(start.x, start.z, self.cell_size)
        end_pos = GridPosition.from_world(end.x, end.z, self.cell_size)

        # Validate positions
        if not self._is_valid_position(start_pos):
            return PathResult(
                found=False,
                path=[],
                length=0,
                width=0,
                message="Start position is out of bounds",
            )
        if not self._is_valid_position(end_pos):
            return PathResult(
                found=False,
                path=[],
                length=0,
                width=0,
                message="End position is out of bounds",
            )

        # A* search
        path = self._a_star(start_pos, end_pos, min_width)

        if not path:
            return PathResult(
                found=False,
                path=[],
                length=0,
                width=0,
                message="No path found between points",
            )

        # Calculate path length
        length = self._calculate_path_length(path)

        return PathResult(
            found=True,
            path=path,
            length=length,
            width=min_width,
            message=f"Path found: {length:.2f}m",
        )

    def find_traffic_path(
        self,
        door1_pos: PathPoint,
        door2_pos: PathPoint,
    ) -> TrafficPath:
        """Find a traffic path between two doors.

        Args:
            door1_pos: First door position.
            door2_pos: Second door position.

        Returns:
            TrafficPath representing the main traffic corridor.
        """
        result = self.find_path(door1_pos, door2_pos, self.MIN_TRAFFIC_WIDTH)

        if not result.found:
            return TrafficPath(
                points=[],
                width=self.MIN_TRAFFIC_WIDTH,
                path_type=PathType.TRAFFIC,
                is_valid=False,
            )

        # Convert grid path to world points
        points = [
            PathPoint(
                x=pos.col * self.cell_size + self.cell_size / 2,
                z=pos.row * self.cell_size + self.cell_size / 2,
            )
            for pos in result.path
        ]

        # Simplify path (remove collinear points)
        simplified = self._simplify_path(points)

        return TrafficPath(
            points=simplified,
            width=self.MIN_TRAFFIC_WIDTH,
            path_type=PathType.TRAFFIC,
            is_valid=True,
        )

    def verify_emergency_exit(
        self,
        furniture_pos: PathPoint,
        door_pos: PathPoint,
    ) -> PathResult:
        """Verify emergency exit accessibility from a furniture position.

        Args:
            furniture_pos: Starting position (e.g., bed).
            door_pos: Door position (exit).

        Returns:
            PathResult with emergency path details.
        """
        return self.find_path(furniture_pos, door_pos, self.MIN_EMERGENCY_WIDTH)

    def check_furniture_access(
        self,
        furniture_box: AABB,
        access_side: str = "front",
    ) -> PathResult:
        """Check if furniture is accessible from a specific side.

        Args:
            furniture_box: Furniture bounding box.
            access_side: Which side to check ("front", "back", "left", "right").

        Returns:
            PathResult indicating accessibility.
        """
        # Calculate access point based on side
        access_point = self._get_access_point(furniture_box, access_side)

        # Try to find path from room entrance area to access point
        # Assume entrance is at the door (we'll check from multiple edges)
        entrance_points = [
            PathPoint(x=0, z=self.room_depth / 2),  # West entrance
            PathPoint(x=self.room_width / 2, z=0),  # North entrance
            PathPoint(x=self.room_width, z=self.room_depth / 2),  # East entrance
            PathPoint(x=self.room_width / 2, z=self.room_depth),  # South entrance
        ]

        for entrance in entrance_points:
            result = self.find_path(entrance, access_point, self.MIN_ACCESS_WIDTH)
            if result.found:
                return result

        return PathResult(
            found=False,
            path=[],
            length=0,
            width=0,
            message=f"Furniture {access_side} side is not accessible",
        )

    def calculate_chi_flow_path(
        self,
        entry_point: PathPoint,
        focal_point: PathPoint,
    ) -> TrafficPath:
        """Calculate chi energy flow path in feng shui.

        Chi should flow smoothly from entry to focal point (e.g., bed headboard).

        Args:
            entry_point: Room entry point (door).
            focal_point: Room focal point (main furniture).

        Returns:
            TrafficPath representing chi flow.
        """
        result = self.find_path(entry_point, focal_point, self.MIN_ACCESS_WIDTH)

        if not result.found:
            return TrafficPath(
                points=[],
                width=self.MIN_ACCESS_WIDTH,
                path_type=PathType.CHI_FLOW,
                is_valid=False,
            )

        points = [
            PathPoint(
                x=pos.col * self.cell_size + self.cell_size / 2,
                z=pos.row * self.cell_size + self.cell_size / 2,
            )
            for pos in result.path
        ]

        return TrafficPath(
            points=self._simplify_path(points),
            width=self.MIN_ACCESS_WIDTH,
            path_type=PathType.CHI_FLOW,
            is_valid=True,
        )

    def get_path_coverage(self) -> float:
        """Get the percentage of room covered by possible paths.

        Returns:
            Fraction of room that is traversable (0.0 to 1.0).
        """
        total_cells = self._grid.rows * self._grid.cols
        traversable = sum(
            1
            for r in range(self._grid.rows)
            for c in range(self._grid.cols)
            if self._grid.get_cell(GridPosition(r, c)) == CellState.EMPTY
        )
        return traversable / total_cells if total_cells > 0 else 0.0

    def _a_star(
        self,
        start: GridPosition,
        end: GridPosition,
        min_width: float,
    ) -> list[GridPosition]:
        """A* pathfinding algorithm.

        Args:
            start: Starting grid position.
            end: Ending grid position.
            min_width: Minimum path width in meters.

        Returns:
            List of grid positions forming the path, or empty if no path.
        """
        # Convert width to cells
        width_cells = max(1, int(min_width / self.cell_size))

        # Priority queue: (f_score, counter, position)
        counter = 0
        open_set: list[tuple[float, int, GridPosition]] = []
        heappush(open_set, (0, counter, start))

        came_from: dict[GridPosition, GridPosition] = {}
        g_score: dict[GridPosition, float] = {start: 0}
        f_score: dict[GridPosition, float] = {start: self._heuristic(start, end)}

        while open_set:
            _, _, current = heappop(open_set)

            if current == end:
                return self._reconstruct_path(came_from, current)

            for neighbor in self._get_neighbors(current):
                if not self._is_passable(neighbor, width_cells):
                    continue

                tentative_g = g_score[current] + self._distance(current, neighbor)

                if neighbor not in g_score or tentative_g < g_score[neighbor]:
                    came_from[neighbor] = current
                    g_score[neighbor] = tentative_g
                    f = tentative_g + self._heuristic(neighbor, end)
                    f_score[neighbor] = f
                    counter += 1
                    heappush(open_set, (f, counter, neighbor))

        return []

    def _heuristic(self, a: GridPosition, b: GridPosition) -> float:
        """Calculate heuristic distance (Euclidean)."""
        dx = abs(a.col - b.col)
        dz = abs(a.row - b.row)
        return (dx * dx + dz * dz) ** 0.5

    def _distance(self, a: GridPosition, b: GridPosition) -> float:
        """Calculate actual distance between adjacent cells."""
        dx = abs(a.col - b.col)
        dz = abs(a.row - b.row)
        if dx + dz == 1:
            return 1.0  # Cardinal direction
        return 1.414  # Diagonal

    def _get_neighbors(self, pos: GridPosition) -> list[GridPosition]:
        """Get valid neighboring positions (8-directional)."""
        neighbors = []
        for dr in [-1, 0, 1]:
            for dc in [-1, 0, 1]:
                if dr == 0 and dc == 0:
                    continue
                neighbor = GridPosition(row=pos.row + dr, col=pos.col + dc)
                if self._is_valid_position(neighbor):
                    neighbors.append(neighbor)
        return neighbors

    def _is_valid_position(self, pos: GridPosition) -> bool:
        """Check if position is within grid bounds."""
        return 0 <= pos.row < self._grid.rows and 0 <= pos.col < self._grid.cols

    def _is_passable(self, pos: GridPosition, width_cells: int = 1) -> bool:
        """Check if a position (and surrounding cells for width) is passable."""
        half = width_cells // 2
        for dr in range(-half, half + 1):
            for dc in range(-half, half + 1):
                check_pos = GridPosition(row=pos.row + dr, col=pos.col + dc)
                if not self._is_valid_position(check_pos):
                    return False
                state = self._grid.get_cell(check_pos)
                if state != CellState.EMPTY and state != CellState.TRAFFIC:
                    return False
        return True

    def _reconstruct_path(
        self,
        came_from: dict[GridPosition, GridPosition],
        current: GridPosition,
    ) -> list[GridPosition]:
        """Reconstruct path from came_from map."""
        path = [current]
        while current in came_from:
            current = came_from[current]
            path.append(current)
        path.reverse()
        return path

    def _calculate_path_length(self, path: list[GridPosition]) -> float:
        """Calculate path length in meters."""
        if len(path) < 2:
            return 0.0
        total = 0.0
        for i in range(len(path) - 1):
            total += self._distance(path[i], path[i + 1]) * self.cell_size
        return total

    def _simplify_path(self, points: list[PathPoint]) -> list[PathPoint]:
        """Simplify path by removing collinear points."""
        if len(points) <= 2:
            return points

        simplified = [points[0]]
        for i in range(1, len(points) - 1):
            p1, p2, p3 = points[i - 1], points[i], points[i + 1]
            # Check if collinear (cross product near zero)
            cross = (p2.x - p1.x) * (p3.z - p1.z) - (p2.z - p1.z) * (p3.x - p1.x)
            if abs(cross) > 0.001:  # Not collinear
                simplified.append(p2)
        simplified.append(points[-1])
        return simplified

    def _get_access_point(self, box: AABB, side: str) -> PathPoint:
        """Get access point for a side of furniture."""
        offset = self.MIN_ACCESS_WIDTH  # Distance from furniture
        if side == "front":
            return PathPoint(x=box.center_x, z=box.max_z + offset)
        if side == "back":
            return PathPoint(x=box.center_x, z=box.min_z - offset)
        if side == "left":
            return PathPoint(x=box.min_x - offset, z=box.center_z)
        if side == "right":
            return PathPoint(x=box.max_x + offset, z=box.center_z)
        # Default to front
        return PathPoint(x=box.center_x, z=box.max_z + offset)


def find_direct_line_path(
    start: PathPoint,
    end: PathPoint,
    obstacles: list[AABB],
) -> bool:
    """Check if a direct line path exists between two points.

    Args:
        start: Starting point.
        end: Ending point.
        obstacles: List of obstacles to avoid.

    Returns:
        True if a direct line path is clear.
    """
    # Create a thin line box between points
    min_x = min(start.x, end.x)
    max_x = max(start.x, end.x)
    min_z = min(start.z, end.z)
    max_z = max(start.z, end.z)

    # Ensure minimum dimension
    if max_x - min_x < 0.01:
        min_x -= 0.01
        max_x += 0.01
    if max_z - min_z < 0.01:
        min_z -= 0.01
        max_z += 0.01

    line_box = AABB(min_x=min_x, min_z=min_z, max_x=max_x, max_z=max_z)

    return all(not line_box.intersects(obstacle) for obstacle in obstacles)


def calculate_path_efficiency(
    actual_length: float,
    direct_distance: float,
) -> float:
    """Calculate path efficiency ratio.

    Args:
        actual_length: Actual path length.
        direct_distance: Direct line distance.

    Returns:
        Efficiency ratio (1.0 = perfect, lower = more winding).
    """
    if actual_length <= 0:
        return 0.0
    return min(1.0, direct_distance / actual_length)
