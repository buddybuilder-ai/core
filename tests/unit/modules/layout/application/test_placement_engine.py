"""Tests for placement engine service."""

import pytest

from src.modules.layout.application.dtos import PlacedFurniture, PlacementStrategy
from src.modules.layout.application.dtos.placement_result import (
    PlacementFailureReason,
    PlacementStatus,
)
from src.modules.layout.application.dtos.spatial_analysis import (
    CommandPosition,
    FengShuiDirection,
    SpatialAnalysisResult,
    ZoneQuality,
)
from src.modules.layout.application.services.furniture_selector import (
    FurnitureSelection,
)
from src.modules.layout.application.services.placement_engine import (
    FallbackStrategy,
    PlacementConfig,
    PlacementEngine,
    RotationStrategy,
)
from src.modules.layout.infrastructure.tools import FurnitureSearchResult


class TestPlacementConfig:
    """Tests for PlacementConfig."""

    def test_default_config(self) -> None:
        """Test default configuration values."""
        config = PlacementConfig()
        assert config.grid_cell_size == 0.1
        assert config.min_clearance == 0.6
        assert config.max_placement_attempts == 100
        assert config.rotation_strategy == RotationStrategy.FOUR_WAY
        assert config.max_occupancy_ratio == 0.7
        assert config.prefer_wall_placement is True

    def test_custom_config(self) -> None:
        """Test custom configuration."""
        config = PlacementConfig(
            grid_cell_size=0.2,
            min_clearance=0.8,
            max_placement_attempts=50,
            rotation_strategy=RotationStrategy.TWO_WAY,
        )
        assert config.grid_cell_size == 0.2
        assert config.min_clearance == 0.8
        assert config.max_placement_attempts == 50
        assert config.rotation_strategy == RotationStrategy.TWO_WAY

    def test_default_fallback_order(self) -> None:
        """Test default fallback order."""
        config = PlacementConfig()
        assert FallbackStrategy.ROTATE in config.fallback_order
        assert FallbackStrategy.MOVE in config.fallback_order
        assert FallbackStrategy.SKIP in config.fallback_order


class TestPlacementEngine:
    """Tests for PlacementEngine."""

    @pytest.fixture
    def engine(self) -> PlacementEngine:
        """Create test placement engine."""
        return PlacementEngine(room_width=5.0, room_depth=4.0)

    @pytest.fixture
    def bed_item(self) -> FurnitureSearchResult:
        """Create test bed item."""
        return FurnitureSearchResult(
            id="bed_001",
            name="Queen Bed",
            category="bed",
            width=1.6,
            depth=2.0,
            height=0.5,
            budget_level="medium",
            is_essential=True,
            clearance_front=0.6,
            clearance_sides=0.3,
            feng_shui_element="wood",
            placement_notes="Place in command position",
            total_footprint=3.2,
        )

    @pytest.fixture
    def bed_selection(self, bed_item: FurnitureSearchResult) -> FurnitureSelection:
        """Create test bed selection."""
        return FurnitureSelection(
            item=bed_item,
            priority=1,
            is_essential=True,
            feng_shui_notes=["Place with headboard against wall"],
        )

    @pytest.fixture
    def nightstand_item(self) -> FurnitureSearchResult:
        """Create test nightstand item."""
        return FurnitureSearchResult(
            id="nightstand_001",
            name="Nightstand",
            category="nightstand",
            width=0.45,
            depth=0.4,
            height=0.55,
            budget_level="low",
            is_essential=False,
            clearance_front=0.3,
            clearance_sides=0.2,
            feng_shui_element="wood",
            placement_notes="Place beside bed",
            total_footprint=0.18,
        )

    @pytest.fixture
    def nightstand_selection(
        self, nightstand_item: FurnitureSearchResult
    ) -> FurnitureSelection:
        """Create test nightstand selection."""
        return FurnitureSelection(
            item=nightstand_item,
            priority=2,
            is_essential=False,
            feng_shui_notes=["Place beside bed"],
        )

    def test_engine_initialization(self, engine: PlacementEngine) -> None:
        """Test engine initialization."""
        assert engine.room_width == 5.0
        assert engine.room_depth == 4.0
        assert engine.config.grid_cell_size == 0.1
        assert len(engine._placed_items) == 0

    def test_place_single_item(
        self,
        engine: PlacementEngine,
        bed_selection: FurnitureSelection,
    ) -> None:
        """Test placing a single furniture item."""
        result = engine.place_item(bed_selection)

        assert result.status == PlacementStatus.SUCCESS
        assert result.furniture is not None
        assert result.furniture.category == "bed"
        assert result.furniture.is_essential is True
        assert len(engine._placed_items) == 1

    def test_place_multiple_items(
        self,
        engine: PlacementEngine,
        bed_selection: FurnitureSelection,
        nightstand_selection: FurnitureSelection,
    ) -> None:
        """Test placing multiple furniture items."""
        result = engine.place_all([bed_selection, nightstand_selection])

        assert result.overall_status in (PlacementStatus.SUCCESS, PlacementStatus.PARTIAL)
        assert result.total_items == 2
        assert result.placed_count >= 1

    def test_place_item_collision_detection(
        self,
        engine: PlacementEngine,
        bed_selection: FurnitureSelection,
    ) -> None:
        """Test that collision detection works."""
        # Place first item
        result1 = engine.place_item(bed_selection)
        assert result1.is_success

        # Create second bed that would overlap
        bed2 = FurnitureSearchResult(
            id="bed_002",
            name="Another Bed",
            category="bed",
            width=1.6,
            depth=2.0,
            height=0.5,
            budget_level="medium",
            is_essential=True,
            clearance_front=0.6,
            clearance_sides=0.3,
            feng_shui_element="wood",
            placement_notes="",
            total_footprint=3.2,
        )
        selection2 = FurnitureSelection(item=bed2, priority=2, is_essential=True)

        # Should still find a different position
        result2 = engine.place_item(selection2)
        # May succeed in different position or fail due to space
        if result2.is_success:
            assert result2.furniture is not None
            # Positions should be different
            assert (
                result2.furniture.pos_x != result1.furniture.pos_x
                or result2.furniture.pos_z != result1.furniture.pos_z
            )

    def test_place_item_out_of_bounds(self) -> None:
        """Test placing item larger than room."""
        engine = PlacementEngine(room_width=1.0, room_depth=1.0)

        large_item = FurnitureSearchResult(
            id="large_bed",
            name="Large Bed",
            category="bed",
            width=2.0,
            depth=2.5,
            height=0.5,
            budget_level="high",
            is_essential=True,
            clearance_front=0.6,
            clearance_sides=0.3,
            feng_shui_element="wood",
            placement_notes="",
            total_footprint=5.0,
        )
        selection = FurnitureSelection(item=large_item, priority=1, is_essential=True)

        result = engine.place_item(selection)
        assert result.status in (PlacementStatus.FAILED, PlacementStatus.SKIPPED)

    def test_rotation_strategy(self) -> None:
        """Test rotation strategies."""
        config = PlacementConfig(rotation_strategy=RotationStrategy.FOUR_WAY)
        engine = PlacementEngine(room_width=3.0, room_depth=4.0, config=config)

        # Item that might need rotation to fit
        item = FurnitureSearchResult(
            id="desk",
            name="Desk",
            category="desk",
            width=1.5,
            depth=0.8,
            height=0.75,
            budget_level="medium",
            is_essential=True,
            clearance_front=0.6,
            clearance_sides=0.3,
            feng_shui_element="wood",
            placement_notes="",
            total_footprint=1.2,
        )
        selection = FurnitureSelection(item=item, priority=1, is_essential=True)

        result = engine.place_item(selection)
        assert result.is_success
        assert result.furniture.rotation in [0, 90, 180, 270]

    def test_essential_items_prioritized(
        self,
        engine: PlacementEngine,
        bed_selection: FurnitureSelection,
        nightstand_selection: FurnitureSelection,
    ) -> None:
        """Test that essential items are prioritized."""
        # Put optional item first in list
        selections = [nightstand_selection, bed_selection]
        result = engine.place_all(selections)

        # Bed should be placed first even though it's second in list
        if result.placed_count > 0:
            first_placed = engine._placed_items[0]
            assert first_placed.is_essential is True


class TestPlacementEngineStrategies:
    """Tests for placement strategies."""

    @pytest.fixture
    def engine(self) -> PlacementEngine:
        """Create test placement engine."""
        return PlacementEngine(room_width=5.0, room_depth=4.0)

    @pytest.fixture
    def spatial_analysis(self) -> SpatialAnalysisResult:
        """Create test spatial analysis result."""
        return SpatialAnalysisResult(
            room_area=20.0,
            usable_area=18.0,
            command_positions=[
                CommandPosition(
                    x=3.5,
                    z=0.5,
                    facing_direction=FengShuiDirection.SOUTH,
                    quality=ZoneQuality.EXCELLENT,
                    has_solid_backing=True,
                    can_see_door=True,
                    score=95.0,
                ),
            ],
        )

    def test_command_position_strategy(
        self,
        engine: PlacementEngine,
        spatial_analysis: SpatialAnalysisResult,
    ) -> None:
        """Test command position placement strategy."""
        bed = FurnitureSearchResult(
            id="bed",
            name="Bed",
            category="bed",
            width=1.6,
            depth=2.0,
            height=0.5,
            budget_level="medium",
            is_essential=True,
            clearance_front=0.6,
            clearance_sides=0.3,
            feng_shui_element="wood",
            placement_notes="",
            total_footprint=3.2,
        )
        selection = FurnitureSelection(item=bed, priority=1, is_essential=True)

        result = engine.place_item(selection, spatial_analysis=spatial_analysis)
        assert result.is_success
        # Should use command position strategy for bed
        assert result.final_strategy in (
            PlacementStrategy.COMMAND_POSITION,
            PlacementStrategy.GRID_BASED,
        )

    def test_wall_aligned_strategy(self, engine: PlacementEngine) -> None:
        """Test wall-aligned placement strategy."""
        bookshelf = FurnitureSearchResult(
            id="bookshelf",
            name="Bookshelf",
            category="bookshelf",
            width=0.8,
            depth=0.3,
            height=1.8,
            budget_level="medium",
            is_essential=False,
            clearance_front=0.5,
            clearance_sides=0.1,
            feng_shui_element="wood",
            placement_notes="",
            total_footprint=0.24,
        )
        selection = FurnitureSelection(item=bookshelf, priority=1, is_essential=False)

        result = engine.place_item(selection)
        assert result.is_success

        # Should be near a wall
        furniture = result.furniture
        near_wall = (
            furniture.pos_x < 1.0
            or furniture.pos_x > engine.room_width - furniture.width - 1.0
            or furniture.pos_z < 1.0
            or furniture.pos_z > engine.room_depth - furniture.depth - 1.0
        )
        assert near_wall or result.final_strategy == PlacementStrategy.GRID_BASED

    def test_center_room_strategy(self, engine: PlacementEngine) -> None:
        """Test center room placement strategy."""
        coffee_table = FurnitureSearchResult(
            id="coffee_table",
            name="Coffee Table",
            category="coffee_table",
            width=1.0,
            depth=0.6,
            height=0.45,
            budget_level="medium",
            is_essential=False,
            clearance_front=0.4,
            clearance_sides=0.4,
            feng_shui_element="wood",
            placement_notes="",
            total_footprint=0.6,
        )
        selection = FurnitureSelection(
            item=coffee_table, priority=1, is_essential=False
        )

        result = engine.place_item(selection)
        assert result.is_success


class TestPlacementEngineFallback:
    """Tests for fallback strategies."""

    @pytest.fixture
    def small_engine(self) -> PlacementEngine:
        """Create small room engine to force fallbacks."""
        config = PlacementConfig(
            fallback_order=[
                FallbackStrategy.ROTATE,
                FallbackStrategy.MOVE,
                FallbackStrategy.SKIP,
            ]
        )
        return PlacementEngine(room_width=3.0, room_depth=3.0, config=config)

    def test_fallback_to_rotation(self, small_engine: PlacementEngine) -> None:
        """Test fallback to rotation strategy."""
        # Long narrow item that might need rotation
        item = FurnitureSearchResult(
            id="sofa",
            name="Sofa",
            category="sofa",
            width=2.0,
            depth=0.8,
            height=0.85,
            budget_level="medium",
            is_essential=True,
            clearance_front=0.6,
            clearance_sides=0.3,
            feng_shui_element="wood",
            placement_notes="",
            total_footprint=1.6,
        )
        selection = FurnitureSelection(item=item, priority=1, is_essential=True)

        result = small_engine.place_item(selection)
        # Should either succeed with rotation or use grid placement
        if result.is_success:
            assert result.furniture is not None

    def test_fallback_to_skip(self) -> None:
        """Test fallback to skip for optional item."""
        # Very small room
        config = PlacementConfig(
            fallback_order=[FallbackStrategy.SKIP],
            max_placement_attempts=5,
        )
        engine = PlacementEngine(room_width=1.5, room_depth=1.5, config=config)

        # Item too large for room
        item = FurnitureSearchResult(
            id="large_sofa",
            name="Large Sofa",
            category="sofa",
            width=2.5,
            depth=1.0,
            height=0.85,
            budget_level="medium",
            is_essential=False,
            clearance_front=0.6,
            clearance_sides=0.3,
            feng_shui_element="wood",
            placement_notes="",
            total_footprint=2.5,
        )
        selection = FurnitureSelection(item=item, priority=1, is_essential=False)

        result = engine.place_item(selection)
        # Should be skipped since it can't fit
        assert result.status in (PlacementStatus.SKIPPED, PlacementStatus.FAILED)


class TestPlacementEngineHelpers:
    """Tests for helper methods."""

    @pytest.fixture
    def engine(self) -> PlacementEngine:
        """Create test placement engine."""
        return PlacementEngine(room_width=5.0, room_depth=4.0)

    def test_get_rotated_dimensions(self, engine: PlacementEngine) -> None:
        """Test dimension rotation."""
        width, depth = engine._get_rotated_dimensions(1.6, 2.0, 0)
        assert width == 1.6
        assert depth == 2.0

        width, depth = engine._get_rotated_dimensions(1.6, 2.0, 90)
        assert width == 2.0
        assert depth == 1.6

        width, depth = engine._get_rotated_dimensions(1.6, 2.0, 180)
        assert width == 1.6
        assert depth == 2.0

        width, depth = engine._get_rotated_dimensions(1.6, 2.0, 270)
        assert width == 2.0
        assert depth == 1.6

    def test_get_occupancy_rate(self, engine: PlacementEngine) -> None:
        """Test occupancy rate calculation."""
        initial_rate = engine.get_occupancy_rate()
        assert initial_rate == 0.0

        # Place an item
        item = FurnitureSearchResult(
            id="desk",
            name="Desk",
            category="desk",
            width=1.0,
            depth=0.6,
            height=0.75,
            budget_level="medium",
            is_essential=True,
            clearance_front=0.6,
            clearance_sides=0.3,
            feng_shui_element="wood",
            placement_notes="",
            total_footprint=0.6,
        )
        selection = FurnitureSelection(item=item, priority=1, is_essential=True)
        engine.place_item(selection)

        new_rate = engine.get_occupancy_rate()
        assert new_rate > 0.0

    def test_get_available_area(self, engine: PlacementEngine) -> None:
        """Test available area calculation."""
        total_area = engine.room_width * engine.room_depth
        initial_available = engine.get_available_area()
        assert initial_available == pytest.approx(total_area, rel=0.01)

    def test_clear_placements(self, engine: PlacementEngine) -> None:
        """Test clearing all placements."""
        # Place an item
        item = FurnitureSearchResult(
            id="chair",
            name="Chair",
            category="chair",
            width=0.5,
            depth=0.5,
            height=0.9,
            budget_level="low",
            is_essential=True,
            clearance_front=0.4,
            clearance_sides=0.2,
            feng_shui_element="metal",
            placement_notes="",
            total_footprint=0.25,
        )
        selection = FurnitureSelection(item=item, priority=1, is_essential=True)
        engine.place_item(selection)

        assert len(engine._placed_items) == 1

        engine.clear()
        assert len(engine._placed_items) == 0
        assert engine.get_occupancy_rate() == 0.0

    def test_to_ascii(self, engine: PlacementEngine) -> None:
        """Test ASCII representation."""
        ascii_repr = engine.to_ascii()
        assert isinstance(ascii_repr, str)
        assert len(ascii_repr) > 0
        # Should contain empty cells
        assert "." in ascii_repr

    def test_get_placed_furniture(self, engine: PlacementEngine) -> None:
        """Test getting placed furniture list."""
        item = FurnitureSearchResult(
            id="lamp",
            name="Lamp",
            category="lamp",
            width=0.3,
            depth=0.3,
            height=1.5,
            budget_level="low",
            is_essential=False,
            clearance_front=0.2,
            clearance_sides=0.1,
            feng_shui_element="fire",
            placement_notes="",
            total_footprint=0.09,
        )
        selection = FurnitureSelection(item=item, priority=1, is_essential=False)
        engine.place_item(selection)

        placed = engine.get_placed_furniture()
        assert len(placed) == 1
        assert placed[0].name == "Lamp"


class TestPlacementEngineContextUpdate:
    """Tests for context update."""

    @pytest.fixture
    def engine(self) -> PlacementEngine:
        """Create test placement engine."""
        return PlacementEngine(room_width=5.0, room_depth=4.0)

    def test_update_context(self, engine: PlacementEngine) -> None:
        """Test updating agent context."""
        from src.modules.layout.application.dtos import AgentContext
        from src.modules.layout.domain.entities import Room, RoomType

        room = Room(
            width=5.0,
            depth=4.0,
            height=2.8,
            room_type=RoomType.BEDROOM,
        )
        context = AgentContext(room=room, room_type="bedroom")

        item = FurnitureSearchResult(
            id="bed",
            name="Bed",
            category="bed",
            width=1.6,
            depth=2.0,
            height=0.5,
            budget_level="medium",
            is_essential=True,
            clearance_front=0.6,
            clearance_sides=0.3,
            feng_shui_element="wood",
            placement_notes="",
            total_footprint=3.2,
        )
        selection = FurnitureSelection(item=item, priority=1, is_essential=True)

        result = engine.place_all([selection])
        engine.update_context(context, result)

        assert len(context.placed_furniture) == 1
        assert "placement" in context.metadata
        assert context.metadata["placement"]["placed_count"] == 1


class TestBatchPlacementResult:
    """Tests for batch placement result."""

    @pytest.fixture
    def engine(self) -> PlacementEngine:
        """Create test placement engine."""
        return PlacementEngine(room_width=6.0, room_depth=5.0)

    def test_batch_placement_success(self, engine: PlacementEngine) -> None:
        """Test successful batch placement."""
        items = [
            FurnitureSearchResult(
                id="desk",
                name="Desk",
                category="desk",
                width=1.2,
                depth=0.6,
                height=0.75,
                budget_level="medium",
                is_essential=True,
                clearance_front=0.6,
                clearance_sides=0.3,
                feng_shui_element="wood",
                placement_notes="",
                total_footprint=0.72,
            ),
            FurnitureSearchResult(
                id="chair",
                name="Chair",
                category="chair",
                width=0.5,
                depth=0.5,
                height=0.9,
                budget_level="low",
                is_essential=True,
                clearance_front=0.4,
                clearance_sides=0.2,
                feng_shui_element="metal",
                placement_notes="",
                total_footprint=0.25,
            ),
        ]
        selections = [
            FurnitureSelection(item=items[0], priority=1, is_essential=True),
            FurnitureSelection(item=items[1], priority=2, is_essential=True),
        ]

        result = engine.place_all(selections)

        assert result.total_items == 2
        assert result.placed_count == 2
        assert result.overall_status == PlacementStatus.SUCCESS
        assert result.success_rate == 1.0
        assert result.execution_time_ms > 0

    def test_batch_placement_partial(self) -> None:
        """Test partial batch placement."""
        # Small room to force some failures
        engine = PlacementEngine(room_width=2.5, room_depth=2.5)

        items = [
            FurnitureSearchResult(
                id="sofa",
                name="Large Sofa",
                category="sofa",
                width=2.0,
                depth=0.9,
                height=0.85,
                budget_level="medium",
                is_essential=True,
                clearance_front=0.6,
                clearance_sides=0.3,
                feng_shui_element="wood",
                placement_notes="",
                total_footprint=1.8,
            ),
            FurnitureSearchResult(
                id="table",
                name="Coffee Table",
                category="coffee_table",
                width=1.0,
                depth=0.6,
                height=0.45,
                budget_level="low",
                is_essential=False,
                clearance_front=0.4,
                clearance_sides=0.2,
                feng_shui_element="wood",
                placement_notes="",
                total_footprint=0.6,
            ),
        ]
        selections = [
            FurnitureSelection(item=items[0], priority=1, is_essential=True),
            FurnitureSelection(item=items[1], priority=2, is_essential=False),
        ]

        result = engine.place_all(selections)

        # Should place at least one item
        assert result.placed_count >= 1
        assert result.total_items == 2

    def test_get_placed_furniture_from_result(self, engine: PlacementEngine) -> None:
        """Test getting placed furniture from result."""
        item = FurnitureSearchResult(
            id="bookshelf",
            name="Bookshelf",
            category="bookshelf",
            width=0.8,
            depth=0.3,
            height=1.8,
            budget_level="medium",
            is_essential=False,
            clearance_front=0.5,
            clearance_sides=0.1,
            feng_shui_element="wood",
            placement_notes="",
            total_footprint=0.24,
        )
        selection = FurnitureSelection(item=item, priority=1, is_essential=False)

        result = engine.place_all([selection])
        placed = result.get_placed_furniture()

        assert len(placed) == 1
        assert placed[0].category == "bookshelf"
