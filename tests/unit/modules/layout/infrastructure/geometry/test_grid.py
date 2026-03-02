"""Tests for Placement Grid."""

import pytest

from src.modules.layout.infrastructure.geometry.grid import (
    CellState,
    GridPosition,
    GridRect,
    PlacementCandidate,
    PlacementGrid,
)


class TestCellState:
    """Tests for CellState enum."""

    def test_cell_states_exist(self) -> None:
        """Test all cell states exist."""
        assert CellState.EMPTY == "empty"
        assert CellState.OCCUPIED == "occupied"
        assert CellState.BLOCKED == "blocked"
        assert CellState.TRAFFIC == "traffic"

    def test_cell_state_values_are_strings(self) -> None:
        """Test that enum values are strings."""
        for state in CellState:
            assert isinstance(state.value, str)


class TestGridPosition:
    """Tests for GridPosition dataclass."""

    def test_create_position(self) -> None:
        """Test creating a grid position."""
        pos = GridPosition(row=5, col=10)
        assert pos.row == 5
        assert pos.col == 10

    def test_position_is_frozen(self) -> None:
        """Test that position is immutable."""
        pos = GridPosition(row=0, col=0)
        with pytest.raises(AttributeError):
            pos.row = 1  # type: ignore

    def test_to_world_coordinates(self) -> None:
        """Test conversion to world coordinates."""
        pos = GridPosition(row=10, col=20)
        x, z = pos.to_world(cell_size=0.1)
        assert x == pytest.approx(2.0)  # col * 0.1
        assert z == pytest.approx(1.0)  # row * 0.1

    def test_from_world_coordinates(self) -> None:
        """Test creation from world coordinates."""
        pos = GridPosition.from_world(x=2.5, z=1.8, cell_size=0.1)
        assert pos.col == 25
        assert pos.row == 18

    def test_from_world_rounds_down(self) -> None:
        """Test that from_world truncates to lower cell."""
        pos = GridPosition.from_world(x=0.99, z=0.99, cell_size=1.0)
        assert pos.col == 0
        assert pos.row == 0


class TestGridRect:
    """Tests for GridRect dataclass."""

    def test_create_rect(self) -> None:
        """Test creating a grid rectangle."""
        rect = GridRect(row=5, col=10, rows=3, cols=4)
        assert rect.row == 5
        assert rect.col == 10
        assert rect.rows == 3
        assert rect.cols == 4

    def test_end_properties(self) -> None:
        """Test end row and column calculations."""
        rect = GridRect(row=5, col=10, rows=3, cols=4)
        assert rect.end_row == 8
        assert rect.end_col == 14

    def test_area(self) -> None:
        """Test area calculation."""
        rect = GridRect(row=0, col=0, rows=5, cols=10)
        assert rect.area == 50

    def test_contains_inside(self) -> None:
        """Test contains for position inside rect."""
        rect = GridRect(row=5, col=5, rows=5, cols=5)
        assert rect.contains(GridPosition(row=7, col=7))

    def test_contains_on_boundary(self) -> None:
        """Test contains for position on boundary."""
        rect = GridRect(row=5, col=5, rows=5, cols=5)
        # Start boundary (inclusive)
        assert rect.contains(GridPosition(row=5, col=5))
        # End boundary (exclusive)
        assert not rect.contains(GridPosition(row=10, col=10))

    def test_contains_outside(self) -> None:
        """Test contains for position outside rect."""
        rect = GridRect(row=5, col=5, rows=5, cols=5)
        assert not rect.contains(GridPosition(row=0, col=0))
        assert not rect.contains(GridPosition(row=20, col=20))

    def test_overlaps_true(self) -> None:
        """Test overlaps when rectangles overlap."""
        rect1 = GridRect(row=0, col=0, rows=5, cols=5)
        rect2 = GridRect(row=3, col=3, rows=5, cols=5)
        assert rect1.overlaps(rect2)
        assert rect2.overlaps(rect1)

    def test_overlaps_adjacent(self) -> None:
        """Test overlaps when rectangles are adjacent (no overlap)."""
        rect1 = GridRect(row=0, col=0, rows=5, cols=5)
        rect2 = GridRect(row=0, col=5, rows=5, cols=5)  # Adjacent on right
        assert not rect1.overlaps(rect2)

    def test_overlaps_separate(self) -> None:
        """Test overlaps when rectangles are separate."""
        rect1 = GridRect(row=0, col=0, rows=5, cols=5)
        rect2 = GridRect(row=10, col=10, rows=5, cols=5)
        assert not rect1.overlaps(rect2)

    def test_positions_iterator(self) -> None:
        """Test iterating over all positions."""
        rect = GridRect(row=0, col=0, rows=2, cols=3)
        positions = list(rect.positions())
        assert len(positions) == 6
        assert GridPosition(row=0, col=0) in positions
        assert GridPosition(row=0, col=2) in positions
        assert GridPosition(row=1, col=2) in positions

    def test_from_world_rect(self) -> None:
        """Test creating from world coordinates."""
        rect = GridRect.from_world_rect(x=1.0, z=2.0, width=0.5, depth=0.3, cell_size=0.1)
        assert rect.col == 10  # x / cell_size
        assert rect.row == 20  # z / cell_size
        assert rect.cols == 5  # round(width / cell_size)
        assert rect.rows == 3  # round(depth / cell_size)

    def test_from_world_rect_minimum_size(self) -> None:
        """Test that from_world_rect creates at least 1x1 rect."""
        rect = GridRect.from_world_rect(x=0, z=0, width=0.01, depth=0.01, cell_size=0.1)
        assert rect.cols >= 1
        assert rect.rows >= 1


class TestPlacementCandidate:
    """Tests for PlacementCandidate dataclass."""

    def test_create_candidate(self) -> None:
        """Test creating a placement candidate."""
        candidate = PlacementCandidate(
            position=GridPosition(row=5, col=10),
            world_x=1.0,
            world_z=0.5,
            score=85.0,
            rotation=90,
        )
        assert candidate.world_x == 1.0
        assert candidate.world_z == 0.5
        assert candidate.score == 85.0
        assert candidate.rotation == 90

    def test_default_values(self) -> None:
        """Test default values."""
        candidate = PlacementCandidate(
            position=GridPosition(row=0, col=0),
            world_x=0,
            world_z=0,
        )
        assert candidate.score == 0.0
        assert candidate.rotation == 0

    def test_comparison_higher_score_first(self) -> None:
        """Test that higher scores sort first."""
        c1 = PlacementCandidate(position=GridPosition(0, 0), world_x=0, world_z=0, score=50)
        c2 = PlacementCandidate(position=GridPosition(0, 0), world_x=0, world_z=0, score=80)
        assert c2 < c1  # Higher score is "less than" for sorting

    def test_sorting(self) -> None:
        """Test sorting candidates by score."""
        candidates = [
            PlacementCandidate(position=GridPosition(0, 0), world_x=0, world_z=0, score=30),
            PlacementCandidate(position=GridPosition(0, 0), world_x=0, world_z=0, score=90),
            PlacementCandidate(position=GridPosition(0, 0), world_x=0, world_z=0, score=60),
        ]
        sorted_candidates = sorted(candidates)
        assert sorted_candidates[0].score == 90
        assert sorted_candidates[1].score == 60
        assert sorted_candidates[2].score == 30


class TestPlacementGrid:
    """Tests for PlacementGrid class."""

    def test_create_grid(self) -> None:
        """Test creating a placement grid."""
        grid = PlacementGrid(width=5.0, depth=4.0, cell_size=0.1)
        assert grid.width == 5.0
        assert grid.depth == 4.0
        assert grid.cell_size == 0.1
        assert grid.cols == 50
        assert grid.rows == 40

    def test_create_grid_default_cell_size(self) -> None:
        """Test default cell size of 0.1m."""
        grid = PlacementGrid(width=1.0, depth=1.0)
        assert grid.cell_size == 0.1
        assert grid.cols == 10
        assert grid.rows == 10

    def test_create_grid_invalid_dimensions(self) -> None:
        """Test that invalid dimensions raise ValueError."""
        with pytest.raises(ValueError, match="Width must be positive"):
            PlacementGrid(width=0, depth=4.0)
        with pytest.raises(ValueError, match="Depth must be positive"):
            PlacementGrid(width=4.0, depth=-1)
        with pytest.raises(ValueError, match="Cell size must be positive"):
            PlacementGrid(width=4.0, depth=4.0, cell_size=0)

    def test_all_cells_start_empty(self) -> None:
        """Test that all cells start as empty."""
        grid = PlacementGrid(width=2.0, depth=2.0, cell_size=0.5)
        for row in grid.cells:
            for cell in row:
                assert cell == CellState.EMPTY


class TestPlacementGridCellOperations:
    """Tests for cell get/set operations."""

    @pytest.fixture
    def grid(self) -> PlacementGrid:
        """Create a test grid."""
        return PlacementGrid(width=5.0, depth=5.0, cell_size=0.5)

    def test_get_cell_valid(self, grid: PlacementGrid) -> None:
        """Test getting a valid cell."""
        state = grid.get_cell(GridPosition(row=0, col=0))
        assert state == CellState.EMPTY

    def test_get_cell_out_of_bounds(self, grid: PlacementGrid) -> None:
        """Test getting out of bounds cell returns None."""
        assert grid.get_cell(GridPosition(row=-1, col=0)) is None
        assert grid.get_cell(GridPosition(row=0, col=-1)) is None
        assert grid.get_cell(GridPosition(row=100, col=0)) is None
        assert grid.get_cell(GridPosition(row=0, col=100)) is None

    def test_set_cell_valid(self, grid: PlacementGrid) -> None:
        """Test setting a valid cell."""
        pos = GridPosition(row=5, col=5)
        result = grid.set_cell(pos, CellState.OCCUPIED)
        assert result is True
        assert grid.get_cell(pos) == CellState.OCCUPIED

    def test_set_cell_out_of_bounds(self, grid: PlacementGrid) -> None:
        """Test setting out of bounds cell returns False."""
        result = grid.set_cell(GridPosition(row=-1, col=0), CellState.OCCUPIED)
        assert result is False

    def test_is_available_empty_cell(self, grid: PlacementGrid) -> None:
        """Test is_available for empty cell."""
        assert grid.is_available(GridPosition(row=0, col=0))

    def test_is_available_occupied_cell(self, grid: PlacementGrid) -> None:
        """Test is_available for occupied cell."""
        pos = GridPosition(row=0, col=0)
        grid.set_cell(pos, CellState.OCCUPIED)
        assert not grid.is_available(pos)

    def test_is_available_blocked_cell(self, grid: PlacementGrid) -> None:
        """Test is_available for blocked cell."""
        pos = GridPosition(row=0, col=0)
        grid.set_cell(pos, CellState.BLOCKED)
        assert not grid.is_available(pos)


class TestPlacementGridRectOperations:
    """Tests for rectangle operations."""

    @pytest.fixture
    def grid(self) -> PlacementGrid:
        """Create a test grid."""
        return PlacementGrid(width=5.0, depth=5.0, cell_size=0.5)

    def test_is_rect_available_empty(self, grid: PlacementGrid) -> None:
        """Test is_rect_available for empty area."""
        rect = GridRect(row=0, col=0, rows=2, cols=2)
        assert grid.is_rect_available(rect)

    def test_is_rect_available_partially_occupied(self, grid: PlacementGrid) -> None:
        """Test is_rect_available when one cell is occupied."""
        grid.set_cell(GridPosition(row=1, col=1), CellState.OCCUPIED)
        rect = GridRect(row=0, col=0, rows=3, cols=3)
        assert not grid.is_rect_available(rect)


class TestPlacementGridMarkOccupied:
    """Tests for mark_occupied method."""

    @pytest.fixture
    def grid(self) -> PlacementGrid:
        """Create a test grid."""
        return PlacementGrid(width=5.0, depth=5.0, cell_size=0.5)

    def test_mark_occupied_success(self, grid: PlacementGrid) -> None:
        """Test marking area as occupied."""
        result = grid.mark_occupied("item1", x=0, z=0, width=1.0, depth=1.0)
        assert result is True
        # Check cells are occupied (1.0m = 2 cells at 0.5m resolution)
        assert grid.get_cell(GridPosition(row=0, col=0)) == CellState.OCCUPIED
        assert grid.get_cell(GridPosition(row=0, col=1)) == CellState.OCCUPIED
        assert grid.get_cell(GridPosition(row=1, col=0)) == CellState.OCCUPIED
        assert grid.get_cell(GridPosition(row=1, col=1)) == CellState.OCCUPIED

    def test_mark_occupied_fails_when_not_available(self, grid: PlacementGrid) -> None:
        """Test mark_occupied fails when area is occupied."""
        grid.mark_occupied("item1", x=0, z=0, width=1.0, depth=1.0)
        result = grid.mark_occupied("item2", x=0.5, z=0.5, width=1.0, depth=1.0)
        assert result is False

    def test_mark_occupied_tracks_item(self, grid: PlacementGrid) -> None:
        """Test that occupied item is tracked for removal."""
        grid.mark_occupied("item1", x=1.0, z=1.0, width=1.0, depth=1.0)
        assert "item1" in grid._item_rects


class TestPlacementGridMarkZones:
    """Tests for mark_blocked and mark_traffic methods."""

    @pytest.fixture
    def grid(self) -> PlacementGrid:
        """Create a test grid."""
        return PlacementGrid(width=5.0, depth=5.0, cell_size=0.5)

    def test_mark_blocked(self, grid: PlacementGrid) -> None:
        """Test marking area as blocked."""
        grid.mark_blocked(x=0, z=0, width=1.0, depth=1.0)
        assert grid.get_cell(GridPosition(row=0, col=0)) == CellState.BLOCKED

    def test_mark_blocked_does_not_overwrite_occupied(self, grid: PlacementGrid) -> None:
        """Test that blocked doesn't overwrite occupied."""
        grid.set_cell(GridPosition(row=0, col=0), CellState.OCCUPIED)
        grid.mark_blocked(x=0, z=0, width=0.5, depth=0.5)
        assert grid.get_cell(GridPosition(row=0, col=0)) == CellState.OCCUPIED

    def test_mark_traffic(self, grid: PlacementGrid) -> None:
        """Test marking area as traffic."""
        grid.mark_traffic(x=0, z=0, width=1.0, depth=0.5)
        assert grid.get_cell(GridPosition(row=0, col=0)) == CellState.TRAFFIC

    def test_mark_traffic_does_not_overwrite_occupied(self, grid: PlacementGrid) -> None:
        """Test that traffic doesn't overwrite occupied."""
        grid.set_cell(GridPosition(row=0, col=0), CellState.OCCUPIED)
        grid.mark_traffic(x=0, z=0, width=0.5, depth=0.5)
        assert grid.get_cell(GridPosition(row=0, col=0)) == CellState.OCCUPIED


class TestPlacementGridRemoveItem:
    """Tests for remove_item method."""

    @pytest.fixture
    def grid(self) -> PlacementGrid:
        """Create a test grid with an item."""
        grid = PlacementGrid(width=5.0, depth=5.0, cell_size=0.5)
        grid.mark_occupied("item1", x=1.0, z=1.0, width=1.0, depth=1.0)
        return grid

    def test_remove_item_success(self, grid: PlacementGrid) -> None:
        """Test removing an existing item."""
        result = grid.remove_item("item1")
        assert result is True
        # Check cells are now empty
        assert grid.get_cell(GridPosition(row=2, col=2)) == CellState.EMPTY

    def test_remove_item_not_found(self, grid: PlacementGrid) -> None:
        """Test removing non-existent item."""
        result = grid.remove_item("nonexistent")
        assert result is False

    def test_remove_item_clears_tracking(self, grid: PlacementGrid) -> None:
        """Test that removed item is no longer tracked."""
        grid.remove_item("item1")
        assert "item1" not in grid._item_rects


class TestPlacementGridFindPositions:
    """Tests for find_available_positions method."""

    @pytest.fixture
    def grid(self) -> PlacementGrid:
        """Create a test grid."""
        return PlacementGrid(width=2.0, depth=2.0, cell_size=0.5)

    def test_find_positions_empty_grid(self, grid: PlacementGrid) -> None:
        """Test finding positions on empty grid."""
        candidates = grid.find_available_positions(width=0.5, depth=0.5)
        # 4x4 grid, 1x1 item = 16 positions
        assert len(candidates) > 0

    def test_find_positions_with_occupied(self, grid: PlacementGrid) -> None:
        """Test finding positions with occupied areas."""
        grid.mark_occupied("item1", x=0, z=0, width=1.0, depth=1.0)
        candidates = grid.find_available_positions(width=0.5, depth=0.5)
        # Should have fewer candidates
        for c in candidates:
            assert c.world_x >= 1.0 or c.world_z >= 1.0

    def test_find_positions_item_too_large(self, grid: PlacementGrid) -> None:
        """Test finding positions when item is too large."""
        candidates = grid.find_available_positions(width=3.0, depth=3.0)
        assert len(candidates) == 0

    def test_find_positions_with_margin(self, grid: PlacementGrid) -> None:
        """Test finding positions with margin."""
        candidates = grid.find_available_positions(width=0.5, depth=0.5, margin=0.5)
        # Larger effective size means fewer positions
        assert len(candidates) < 16

    def test_find_positions_world_coordinates(self, grid: PlacementGrid) -> None:
        """Test that world coordinates are correct."""
        candidates = grid.find_available_positions(width=0.5, depth=0.5)
        for c in candidates:
            # Coordinates should be within room bounds
            assert 0 <= c.world_x < grid.width
            assert 0 <= c.world_z < grid.depth


class TestPlacementGridFindBestPosition:
    """Tests for find_best_position method."""

    @pytest.fixture
    def grid(self) -> PlacementGrid:
        """Create a test grid."""
        return PlacementGrid(width=4.0, depth=4.0, cell_size=0.5)

    def test_find_best_position_with_default_scoring(self, grid: PlacementGrid) -> None:
        """Test finding best position with default scoring."""
        result = grid.find_best_position(width=0.5, depth=0.5)
        assert result is not None
        assert isinstance(result, PlacementCandidate)

    def test_find_best_position_custom_scoring(self, grid: PlacementGrid) -> None:
        """Test finding best position with custom scoring."""

        def prefer_corner(x: float, z: float, w: float, d: float) -> float:
            # Prefer top-left corner
            return -(x + z)

        result = grid.find_best_position(width=0.5, depth=0.5, score_func=prefer_corner)
        assert result is not None
        assert result.world_x == pytest.approx(0.0)
        assert result.world_z == pytest.approx(0.0)

    def test_find_best_position_no_space(self, grid: PlacementGrid) -> None:
        """Test finding best position when no space available."""
        # Fill the entire grid
        for row in range(grid.rows):
            for col in range(grid.cols):
                grid.set_cell(GridPosition(row, col), CellState.OCCUPIED)

        result = grid.find_best_position(width=0.5, depth=0.5)
        assert result is None

    def test_find_best_position_with_margin(self, grid: PlacementGrid) -> None:
        """Test finding best position with margin."""
        result = grid.find_best_position(width=0.5, depth=0.5, margin=0.25)
        assert result is not None
        # Position should account for margin
        assert result.world_x >= 0.25 or result.world_z >= 0.25


class TestPlacementGridStatistics:
    """Tests for grid statistics methods."""

    @pytest.fixture
    def grid(self) -> PlacementGrid:
        """Create a test grid."""
        return PlacementGrid(width=2.0, depth=2.0, cell_size=0.5)

    def test_get_occupancy_rate_empty(self, grid: PlacementGrid) -> None:
        """Test occupancy rate on empty grid."""
        rate = grid.get_occupancy_rate()
        assert rate == 0.0

    def test_get_occupancy_rate_partial(self, grid: PlacementGrid) -> None:
        """Test occupancy rate with some occupied cells."""
        # Grid is 4x4 = 16 cells
        # Mark 1m x 1m = 4 cells as occupied
        grid.mark_occupied("item1", x=0, z=0, width=1.0, depth=1.0)
        rate = grid.get_occupancy_rate()
        assert rate == pytest.approx(0.25)  # 4/16

    def test_get_occupancy_rate_includes_blocked(self, grid: PlacementGrid) -> None:
        """Test that occupancy rate includes blocked cells."""
        grid.mark_blocked(x=0, z=0, width=1.0, depth=1.0)
        rate = grid.get_occupancy_rate()
        assert rate > 0

    def test_get_available_area_empty(self, grid: PlacementGrid) -> None:
        """Test available area on empty grid."""
        area = grid.get_available_area()
        assert area == pytest.approx(4.0)  # 2m x 2m

    def test_get_available_area_partial(self, grid: PlacementGrid) -> None:
        """Test available area with occupied space."""
        grid.mark_occupied("item1", x=0, z=0, width=1.0, depth=1.0)
        area = grid.get_available_area()
        assert area == pytest.approx(3.0)  # 4.0 - 1.0


class TestPlacementGridUtilities:
    """Tests for utility methods."""

    @pytest.fixture
    def grid(self) -> PlacementGrid:
        """Create a test grid."""
        grid = PlacementGrid(width=2.0, depth=2.0, cell_size=0.5)
        grid.mark_occupied("item1", x=0, z=0, width=1.0, depth=1.0)
        return grid

    def test_clear(self, grid: PlacementGrid) -> None:
        """Test clearing the grid."""
        grid.clear()
        assert grid.get_occupancy_rate() == 0.0
        assert "item1" not in grid._item_rects

    def test_clone(self, grid: PlacementGrid) -> None:
        """Test cloning the grid."""
        cloned = grid.clone()
        # Check same state
        assert cloned.width == grid.width
        assert cloned.depth == grid.depth
        assert cloned.get_occupancy_rate() == grid.get_occupancy_rate()
        # Check independence
        cloned.clear()
        assert grid.get_occupancy_rate() > 0

    def test_clone_preserves_item_rects(self, grid: PlacementGrid) -> None:
        """Test that clone preserves item tracking."""
        cloned = grid.clone()
        assert "item1" in cloned._item_rects

    def test_to_ascii_empty(self) -> None:
        """Test ASCII representation of empty grid."""
        grid = PlacementGrid(width=1.0, depth=1.0, cell_size=0.5)
        ascii_repr = grid.to_ascii()
        assert ascii_repr == "..\n.."

    def test_to_ascii_with_states(self) -> None:
        """Test ASCII representation with different states."""
        grid = PlacementGrid(width=1.0, depth=1.0, cell_size=0.5)
        grid.set_cell(GridPosition(0, 0), CellState.OCCUPIED)
        grid.set_cell(GridPosition(0, 1), CellState.BLOCKED)
        grid.set_cell(GridPosition(1, 0), CellState.TRAFFIC)
        ascii_repr = grid.to_ascii()
        assert "#X" in ascii_repr
        assert "~." in ascii_repr


class TestPlacementGridIntegration:
    """Integration tests for PlacementGrid."""

    def test_furniture_placement_workflow(self) -> None:
        """Test typical furniture placement workflow."""
        # Create room grid
        grid = PlacementGrid(width=5.0, depth=4.0, cell_size=0.1)

        # Mark door swing zone as blocked
        grid.mark_blocked(x=0, z=1.5, width=0.9, depth=0.9)

        # Mark window zone (no furniture placement)
        grid.mark_blocked(x=2.0, z=0, width=1.5, depth=0.3)

        # Mark traffic path
        grid.mark_traffic(x=0, z=0, width=0.6, depth=4.0)

        # Place a bed (2.0 x 1.8m)
        result = grid.mark_occupied("bed", x=1.0, z=1.0, width=2.0, depth=1.8)
        assert result is True

        # Try to place overlapping item
        result = grid.mark_occupied("dresser", x=2.0, z=1.5, width=1.0, depth=0.5)
        assert result is False

        # Place non-overlapping item
        result = grid.mark_occupied("dresser", x=3.5, z=1.0, width=1.0, depth=0.5)
        assert result is True

        # Check occupancy
        assert grid.get_occupancy_rate() > 0

    def test_find_position_for_new_furniture(self) -> None:
        """Test finding position for additional furniture."""
        grid = PlacementGrid(width=4.0, depth=3.0, cell_size=0.1)

        # Place existing furniture
        grid.mark_occupied("sofa", x=0.5, z=0.5, width=2.0, depth=0.8)

        # Find position for new item
        def prefer_against_wall(x: float, z: float, w: float, d: float) -> float:
            # Prefer positions at edges
            edge_dist = min(x, z, grid.width - x - w, grid.depth - z - d)
            return -edge_dist if edge_dist > 0 else 100

        result = grid.find_best_position(width=0.6, depth=0.4, score_func=prefer_against_wall)

        assert result is not None
        # Should not overlap with sofa
        sofa_rect = GridRect.from_world_rect(0.5, 0.5, 2.0, 0.8, 0.1)
        item_rect = GridRect.from_world_rect(result.world_x, result.world_z, 0.6, 0.4, 0.1)
        assert not sofa_rect.overlaps(item_rect)

    def test_rotation_based_placement(self) -> None:
        """Test placing items with rotation consideration."""
        grid = PlacementGrid(width=3.0, depth=3.0, cell_size=0.1)

        # Item dimensions: 2.0 x 0.8m
        # At 0 rotation, needs 2.0m width
        width_0 = 2.0
        depth_0 = 0.8

        # At 90 rotation, needs 0.8m width
        width_90 = 0.8
        depth_90 = 2.0

        # Find positions for both rotations
        candidates_0 = grid.find_available_positions(width_0, depth_0)
        candidates_90 = grid.find_available_positions(width_90, depth_90)

        # Both should find positions
        assert len(candidates_0) > 0
        assert len(candidates_90) > 0

        # 90 rotation should have more options in narrow space
        # (not always true, depends on room shape)
