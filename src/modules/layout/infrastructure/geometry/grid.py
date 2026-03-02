"""Placement grid for feng shui layout generation."""

from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from enum import StrEnum


class CellState(StrEnum):
    """State of a grid cell."""

    EMPTY = "empty"
    OCCUPIED = "occupied"
    BLOCKED = "blocked"  # Reserved areas (door swing, clearance zones)
    TRAFFIC = "traffic"  # Traffic paths


@dataclass(frozen=True)
class GridPosition:
    """A position on the grid.

    Attributes:
        row: Row index (corresponds to Z axis / depth).
        col: Column index (corresponds to X axis / width).
    """

    row: int
    col: int

    def to_world(self, cell_size: float) -> tuple[float, float]:
        """Convert grid position to world coordinates (x, z).

        Args:
            cell_size: Size of each cell in meters.

        Returns:
            Tuple of (x, z) world coordinates.
        """
        return (self.col * cell_size, self.row * cell_size)

    @classmethod
    def from_world(cls, x: float, z: float, cell_size: float) -> "GridPosition":
        """Create grid position from world coordinates.

        Args:
            x: X coordinate in meters.
            z: Z coordinate in meters.
            cell_size: Size of each cell in meters.

        Returns:
            GridPosition corresponding to the world coordinates.
        """
        return cls(row=int(z / cell_size), col=int(x / cell_size))


@dataclass(frozen=True)
class GridRect:
    """A rectangular area on the grid.

    Attributes:
        row: Starting row (top).
        col: Starting column (left).
        rows: Number of rows (height in cells).
        cols: Number of columns (width in cells).
    """

    row: int
    col: int
    rows: int
    cols: int

    @property
    def end_row(self) -> int:
        """Get the ending row (exclusive)."""
        return self.row + self.rows

    @property
    def end_col(self) -> int:
        """Get the ending column (exclusive)."""
        return self.col + self.cols

    @property
    def area(self) -> int:
        """Get the area in cells."""
        return self.rows * self.cols

    def contains(self, pos: GridPosition) -> bool:
        """Check if a position is within this rectangle."""
        return self.row <= pos.row < self.end_row and self.col <= pos.col < self.end_col

    def overlaps(self, other: "GridRect") -> bool:
        """Check if this rectangle overlaps with another."""
        return not (
            self.end_col <= other.col
            or other.end_col <= self.col
            or self.end_row <= other.row
            or other.end_row <= self.row
        )

    def positions(self) -> Iterator[GridPosition]:
        """Iterate over all positions in this rectangle."""
        for r in range(self.row, self.end_row):
            for c in range(self.col, self.end_col):
                yield GridPosition(row=r, col=c)

    @classmethod
    def from_world_rect(
        cls,
        x: float,
        z: float,
        width: float,
        depth: float,
        cell_size: float,
    ) -> "GridRect":
        """Create grid rect from world coordinates.

        Args:
            x: X coordinate of top-left corner.
            z: Z coordinate of top-left corner.
            width: Width in meters.
            depth: Depth in meters.
            cell_size: Size of each cell in meters.

        Returns:
            GridRect representing the area.
        """
        col = int(x / cell_size)
        row = int(z / cell_size)
        cols = max(1, int(round(width / cell_size)))
        rows = max(1, int(round(depth / cell_size)))
        return cls(row=row, col=col, rows=rows, cols=cols)


@dataclass
class PlacementCandidate:
    """A candidate position for furniture placement.

    Attributes:
        position: Grid position.
        world_x: X coordinate in meters.
        world_z: Z coordinate in meters.
        score: Score for this position (higher is better).
        rotation: Rotation in degrees (0, 90, 180, 270).
    """

    position: GridPosition
    world_x: float
    world_z: float
    score: float = 0.0
    rotation: int = 0

    def __lt__(self, other: "PlacementCandidate") -> bool:
        """Compare by score for sorting."""
        return self.score > other.score  # Higher score is better


@dataclass
class PlacementGrid:
    """Grid-based placement system for furniture.

    Uses a 2D grid to track occupied and available spaces.
    Default resolution is 10cm (0.1m) per cell.

    Attributes:
        width: Room width in meters.
        depth: Room depth in meters.
        cell_size: Size of each cell in meters.
        rows: Number of rows in the grid.
        cols: Number of columns in the grid.
        cells: 2D array of cell states.
    """

    width: float
    depth: float
    cell_size: float = 0.1  # 10cm default
    rows: int = field(init=False)
    cols: int = field(init=False)
    cells: list[list[CellState]] = field(init=False)
    _item_rects: dict[str, GridRect] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        """Initialize the grid."""
        if self.width <= 0:
            raise ValueError("Width must be positive")
        if self.depth <= 0:
            raise ValueError("Depth must be positive")
        if self.cell_size <= 0:
            raise ValueError("Cell size must be positive")

        self.cols = int(round(self.width / self.cell_size))
        self.rows = int(round(self.depth / self.cell_size))

        # Initialize all cells as empty
        self.cells = [[CellState.EMPTY for _ in range(self.cols)] for _ in range(self.rows)]

    def get_cell(self, pos: GridPosition) -> CellState | None:
        """Get the state of a cell.

        Args:
            pos: Grid position to check.

        Returns:
            Cell state, or None if out of bounds.
        """
        if not self._is_valid_position(pos):
            return None
        return self.cells[pos.row][pos.col]

    def set_cell(self, pos: GridPosition, state: CellState) -> bool:
        """Set the state of a cell.

        Args:
            pos: Grid position to set.
            state: New cell state.

        Returns:
            True if successful, False if out of bounds.
        """
        if not self._is_valid_position(pos):
            return False
        self.cells[pos.row][pos.col] = state
        return True

    def is_available(self, pos: GridPosition) -> bool:
        """Check if a cell is available for placement.

        Args:
            pos: Grid position to check.

        Returns:
            True if the cell is empty, False otherwise.
        """
        state = self.get_cell(pos)
        return state == CellState.EMPTY

    def is_rect_available(self, rect: GridRect) -> bool:
        """Check if an entire rectangle is available.

        Args:
            rect: Grid rectangle to check.

        Returns:
            True if all cells in the rectangle are empty.
        """
        return all(self.is_available(pos) for pos in rect.positions())

    def mark_occupied(
        self,
        item_id: str,
        x: float,
        z: float,
        width: float,
        depth: float,
    ) -> bool:
        """Mark cells as occupied by a furniture item.

        Args:
            item_id: Unique identifier for the item.
            x: X position in meters.
            z: Z position in meters.
            width: Item width in meters.
            depth: Item depth in meters.

        Returns:
            True if successful, False if area is not fully available.
        """
        rect = GridRect.from_world_rect(x, z, width, depth, self.cell_size)

        # Check if area is available
        if not self.is_rect_available(rect):
            return False

        # Mark all cells as occupied
        for pos in rect.positions():
            self.set_cell(pos, CellState.OCCUPIED)

        # Store the rect for later removal
        self._item_rects[item_id] = rect
        return True

    def mark_blocked(self, x: float, z: float, width: float, depth: float) -> None:
        """Mark cells as blocked (reserved area).

        Args:
            x: X position in meters.
            z: Z position in meters.
            width: Width in meters.
            depth: Depth in meters.
        """
        rect = GridRect.from_world_rect(x, z, width, depth, self.cell_size)
        for pos in rect.positions():
            if self._is_valid_position(pos):
                # Only block if empty (don't overwrite occupied)
                if self.cells[pos.row][pos.col] == CellState.EMPTY:
                    self.cells[pos.row][pos.col] = CellState.BLOCKED

    def mark_traffic(self, x: float, z: float, width: float, depth: float) -> None:
        """Mark cells as traffic path.

        Args:
            x: X position in meters.
            z: Z position in meters.
            width: Width in meters.
            depth: Depth in meters.
        """
        rect = GridRect.from_world_rect(x, z, width, depth, self.cell_size)
        for pos in rect.positions():
            if self._is_valid_position(pos):
                # Only mark traffic if empty
                if self.cells[pos.row][pos.col] == CellState.EMPTY:
                    self.cells[pos.row][pos.col] = CellState.TRAFFIC

    def remove_item(self, item_id: str) -> bool:
        """Remove an item from the grid.

        Args:
            item_id: ID of the item to remove.

        Returns:
            True if item was found and removed.
        """
        if item_id not in self._item_rects:
            return False

        rect = self._item_rects[item_id]
        for pos in rect.positions():
            self.set_cell(pos, CellState.EMPTY)

        del self._item_rects[item_id]
        return True

    def find_available_positions(
        self,
        width: float,
        depth: float,
        *,
        margin: float = 0.0,
    ) -> list[PlacementCandidate]:
        """Find all positions where an item can be placed.

        Args:
            width: Item width in meters.
            depth: Item depth in meters.
            margin: Additional margin around item in meters.

        Returns:
            List of available placement candidates.
        """
        candidates: list[PlacementCandidate] = []

        # Convert dimensions to grid cells
        item_cols = max(1, int(round((width + margin * 2) / self.cell_size)))
        item_rows = max(1, int(round((depth + margin * 2) / self.cell_size)))

        # Scan grid for available positions
        for row in range(self.rows - item_rows + 1):
            for col in range(self.cols - item_cols + 1):
                rect = GridRect(row=row, col=col, rows=item_rows, cols=item_cols)
                if self.is_rect_available(rect):
                    # Calculate world position (center item, account for margin)
                    world_x = col * self.cell_size + margin
                    world_z = row * self.cell_size + margin
                    candidates.append(
                        PlacementCandidate(
                            position=GridPosition(row=row, col=col),
                            world_x=world_x,
                            world_z=world_z,
                        )
                    )

        return candidates

    def find_best_position(
        self,
        width: float,
        depth: float,
        *,
        score_func: Callable[[float, float, float, float], float] | None = None,
        margin: float = 0.0,
    ) -> PlacementCandidate | None:
        """Find the best position for an item.

        Args:
            width: Item width in meters.
            depth: Item depth in meters.
            score_func: Optional function to score positions.
                       Takes (x, z, width, depth) and returns float.
            margin: Additional margin around item.

        Returns:
            Best placement candidate, or None if no space available.
        """
        candidates = self.find_available_positions(width, depth, margin=margin)

        if not candidates:
            return None

        if score_func is None:
            # Default scoring: prefer positions away from edges
            def default_score(x: float, z: float, w: float, d: float) -> float:
                center_x = x + w / 2
                center_z = z + d / 2
                # Distance from center of room
                room_center_x = self.width / 2
                room_center_z = self.depth / 2
                dist_to_center = (
                    (center_x - room_center_x) ** 2 + (center_z - room_center_z) ** 2
                ) ** 0.5
                # Prefer positions closer to walls but not too close
                edge_dist = min(x, z, self.width - x - w, self.depth - z - d)
                return edge_dist * 0.5 - dist_to_center * 0.3

            score_func = default_score

        # Score all candidates
        for candidate in candidates:
            candidate.score = score_func(candidate.world_x, candidate.world_z, width, depth)

        # Sort by score (highest first) and return best
        candidates.sort()
        return candidates[0]

    def get_occupancy_rate(self) -> float:
        """Get the occupancy rate of the grid.

        Returns:
            Fraction of cells that are occupied (0.0 to 1.0).
        """
        total_cells = self.rows * self.cols
        occupied = sum(
            1
            for row in self.cells
            for cell in row
            if cell in (CellState.OCCUPIED, CellState.BLOCKED)
        )
        return occupied / total_cells if total_cells > 0 else 0.0

    def get_available_area(self) -> float:
        """Get the total available area in square meters.

        Returns:
            Available area in square meters.
        """
        empty_cells = sum(1 for row in self.cells for cell in row if cell == CellState.EMPTY)
        return empty_cells * self.cell_size * self.cell_size

    def clear(self) -> None:
        """Clear the grid, resetting all cells to empty."""
        for row in range(self.rows):
            for col in range(self.cols):
                self.cells[row][col] = CellState.EMPTY
        self._item_rects.clear()

    def clone(self) -> "PlacementGrid":
        """Create a deep copy of this grid.

        Returns:
            New PlacementGrid with the same state.
        """
        new_grid = PlacementGrid(
            width=self.width,
            depth=self.depth,
            cell_size=self.cell_size,
        )
        for row in range(self.rows):
            for col in range(self.cols):
                new_grid.cells[row][col] = self.cells[row][col]
        new_grid._item_rects = dict(self._item_rects)
        return new_grid

    def to_ascii(self) -> str:
        """Generate ASCII representation of the grid.

        Returns:
            String representation using characters:
            . = empty, # = occupied, X = blocked, ~ = traffic
        """
        char_map = {
            CellState.EMPTY: ".",
            CellState.OCCUPIED: "#",
            CellState.BLOCKED: "X",
            CellState.TRAFFIC: "~",
        }
        lines = []
        for row in self.cells:
            lines.append("".join(char_map[cell] for cell in row))
        return "\n".join(lines)

    def _is_valid_position(self, pos: GridPosition) -> bool:
        """Check if a position is within grid bounds."""
        return 0 <= pos.row < self.rows and 0 <= pos.col < self.cols
