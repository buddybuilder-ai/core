"""Tests for Furniture Selector Service."""

import pytest

from src.modules.layout.application.dtos import AgentContext, UserPreferences
from src.modules.layout.application.services import (
    FurnitureSelection,
    FurnitureSelectionResult,
    FurnitureSelector,
)
from src.modules.layout.domain.entities import Room, RoomType
from src.modules.layout.infrastructure.tools import (
    FurnitureSearchInput,
    FurnitureSearchOutput,
    FurnitureSearchResult,
    InMemoryFurnitureDbTool,
)
from src.modules.layout.infrastructure.tools.base import ToolResult


class MockFurnitureDbTool(InMemoryFurnitureDbTool):
    """Mock furniture database tool for testing."""

    async def execute(
        self, input_data: FurnitureSearchInput
    ) -> ToolResult[FurnitureSearchOutput]:
        """Execute mock furniture query using parent implementation."""
        return await super().execute(input_data)


class TestFurnitureSelection:
    """Tests for FurnitureSelection dataclass."""

    @pytest.fixture
    def item(self) -> FurnitureSearchResult:
        """Create test furniture item."""
        return FurnitureSearchResult(
            id="test_bed",
            name="Test Bed",
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

    def test_create_selection(self, item: FurnitureSearchResult) -> None:
        """Test creating furniture selection."""
        selection = FurnitureSelection(
            item=item,
            priority=1,
            is_essential=True,
        )
        assert selection.item == item
        assert selection.priority == 1
        assert selection.is_essential

    def test_to_dict(self, item: FurnitureSearchResult) -> None:
        """Test converting to dictionary."""
        selection = FurnitureSelection(
            item=item,
            priority=1,
            is_essential=True,
            feng_shui_notes=["Place in command position"],
        )
        d = selection.to_dict()
        assert d["id"] == "test_bed"
        assert d["is_essential"] is True
        assert len(d["feng_shui_notes"]) == 1


class TestFurnitureSelectionResult:
    """Tests for FurnitureSelectionResult dataclass."""

    @pytest.fixture
    def selections(self) -> list[FurnitureSelection]:
        """Create test selections."""
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
            placement_notes="Place in command position",
            total_footprint=3.2,
        )
        nightstand = FurnitureSearchResult(
            id="nightstand",
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
        return [
            FurnitureSelection(item=bed, priority=1, is_essential=True),
            FurnitureSelection(item=nightstand, priority=2, is_essential=False),
        ]

    def test_essential_count(self, selections: list[FurnitureSelection]) -> None:
        """Test essential count property."""
        result = FurnitureSelectionResult(selections=selections)
        assert result.essential_count == 1

    def test_optional_count(self, selections: list[FurnitureSelection]) -> None:
        """Test optional count property."""
        result = FurnitureSelectionResult(selections=selections)
        assert result.optional_count == 1

    def test_get_by_priority(self, selections: list[FurnitureSelection]) -> None:
        """Test getting selections by priority."""
        result = FurnitureSelectionResult(selections=selections)
        sorted_selections = result.get_by_priority()
        assert sorted_selections[0].priority == 1
        assert sorted_selections[1].priority == 2

    def test_get_essential(self, selections: list[FurnitureSelection]) -> None:
        """Test getting essential selections."""
        result = FurnitureSelectionResult(selections=selections)
        essential = result.get_essential()
        assert len(essential) == 1
        assert essential[0].item.id == "bed"

    def test_get_by_category(self, selections: list[FurnitureSelection]) -> None:
        """Test getting selections by category."""
        result = FurnitureSelectionResult(selections=selections)
        beds = result.get_by_category("bed")
        assert len(beds) == 1


class TestFurnitureSelector:
    """Tests for FurnitureSelector service."""

    @pytest.fixture
    def mock_tool(self) -> MockFurnitureDbTool:
        """Create mock furniture tool."""
        return MockFurnitureDbTool()

    @pytest.fixture
    def selector(self, mock_tool: MockFurnitureDbTool) -> FurnitureSelector:
        """Create furniture selector instance."""
        return FurnitureSelector(furniture_tool=mock_tool)

    @pytest.mark.asyncio
    async def test_select_furniture_bedroom(
        self, selector: FurnitureSelector
    ) -> None:
        """Test selecting furniture for bedroom."""
        result = await selector.select_furniture(
            room_type="bedroom",
            usable_area=15.0,
        )
        assert len(result.selections) > 0
        # Bed should be selected as essential
        beds = result.get_by_category("bed")
        assert len(beds) == 1
        assert beds[0].is_essential

    @pytest.mark.asyncio
    async def test_select_furniture_office(
        self, selector: FurnitureSelector
    ) -> None:
        """Test selecting furniture for office."""
        result = await selector.select_furniture(
            room_type="office",
            usable_area=12.0,
        )
        assert len(result.selections) > 0
        # Desk and chair should be essential
        essential = result.get_essential()
        categories = [s.item.category for s in essential]
        assert "desk" in categories
        assert "chair" in categories

    @pytest.mark.asyncio
    async def test_select_furniture_living_room(
        self, selector: FurnitureSelector
    ) -> None:
        """Test selecting furniture for living room."""
        result = await selector.select_furniture(
            room_type="living_room",
            usable_area=20.0,
        )
        assert len(result.selections) > 0
        # Sofa should be essential
        sofas = result.get_by_category("sofa")
        assert len(sofas) == 1

    @pytest.mark.asyncio
    async def test_select_furniture_with_preferences(
        self, selector: FurnitureSelector
    ) -> None:
        """Test selecting furniture with user preferences."""
        preferences = UserPreferences(
            style_preference="modern",
            budget_level="medium",
        )
        result = await selector.select_furniture(
            room_type="bedroom",
            usable_area=15.0,
            preferences=preferences,
        )
        assert len(result.selections) > 0

    @pytest.mark.asyncio
    async def test_select_furniture_limited_space(
        self, selector: FurnitureSelector
    ) -> None:
        """Test selecting furniture with limited space."""
        result = await selector.select_furniture(
            room_type="bedroom",
            usable_area=5.0,  # Small area
        )
        # Should still select some items or have warnings
        assert len(result.selections) > 0 or len(result.warnings) > 0

    @pytest.mark.asyncio
    async def test_select_furniture_max_items(
        self, selector: FurnitureSelector
    ) -> None:
        """Test selecting furniture with max items limit."""
        result = await selector.select_furniture(
            room_type="bedroom",
            usable_area=20.0,
            max_items=2,
        )
        assert len(result.selections) <= 2

    @pytest.mark.asyncio
    async def test_feng_shui_notes_included(
        self, selector: FurnitureSelector
    ) -> None:
        """Test feng shui notes are included for relevant items."""
        result = await selector.select_furniture(
            room_type="bedroom",
            usable_area=15.0,
        )
        bed_selection = next(
            (s for s in result.selections if s.item.category == "bed"),
            None,
        )
        assert bed_selection is not None
        assert len(bed_selection.feng_shui_notes) > 0

    @pytest.mark.asyncio
    async def test_total_area_calculated(
        self, selector: FurnitureSelector
    ) -> None:
        """Test total area needed is calculated."""
        result = await selector.select_furniture(
            room_type="bedroom",
            usable_area=15.0,
        )
        # Total area should be positive if items were selected
        if result.selections:
            assert result.total_area_needed > 0


class TestFurnitureSelectorUpdateContext:
    """Tests for FurnitureSelector context update."""

    @pytest.fixture
    def mock_tool(self) -> MockFurnitureDbTool:
        """Create mock furniture tool."""
        return MockFurnitureDbTool()

    @pytest.fixture
    def selector(self, mock_tool: MockFurnitureDbTool) -> FurnitureSelector:
        """Create furniture selector instance."""
        return FurnitureSelector(furniture_tool=mock_tool)

    @pytest.fixture
    def context(self) -> AgentContext:
        """Create test context."""
        room = Room(width=5.0, depth=4.0, room_type=RoomType.BEDROOM)
        return AgentContext(room=room, room_type="bedroom")

    @pytest.mark.asyncio
    async def test_update_context(
        self,
        selector: FurnitureSelector,
        context: AgentContext,
    ) -> None:
        """Test updating context with selection results."""
        result = await selector.select_furniture(
            room_type="bedroom",
            usable_area=15.0,
        )
        selector.update_context(context, result)

        assert len(context.selected_furniture) > 0
        assert "furniture_selection" in context.metadata

    @pytest.mark.asyncio
    async def test_context_has_selection_metadata(
        self,
        selector: FurnitureSelector,
        context: AgentContext,
    ) -> None:
        """Test context metadata includes selection info."""
        result = await selector.select_furniture(
            room_type="bedroom",
            usable_area=15.0,
        )
        selector.update_context(context, result)

        metadata = context.metadata["furniture_selection"]
        assert "total_items" in metadata
        assert "essential_items" in metadata
        assert "total_area_needed" in metadata


class TestFurnitureSelectorHelpers:
    """Tests for FurnitureSelector helper methods."""

    @pytest.fixture
    def mock_tool(self) -> MockFurnitureDbTool:
        """Create mock furniture tool."""
        return MockFurnitureDbTool()

    @pytest.fixture
    def selector(self, mock_tool: MockFurnitureDbTool) -> FurnitureSelector:
        """Create furniture selector instance."""
        return FurnitureSelector(furniture_tool=mock_tool)

    def test_select_essential_only(self, selector: FurnitureSelector) -> None:
        """Test selecting only essential furniture."""
        items = [
            FurnitureSearchResult(
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
                placement_notes="Place in command position",
                total_footprint=3.2,
            ),
            FurnitureSearchResult(
                id="nightstand",
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
            ),
        ]
        selections = selector.select_essential_only("bedroom", items)
        assert len(selections) == 1
        assert selections[0].item.category == "bed"
        assert selections[0].is_essential

    def test_get_furniture_for_zone(self, selector: FurnitureSelector) -> None:
        """Test getting furniture categories for zones."""
        work_furniture = selector.get_furniture_for_zone("work", "office")
        assert "desk" in work_furniture
        assert "chair" in work_furniture

        rest_furniture = selector.get_furniture_for_zone("rest", "bedroom")
        assert "bed" in rest_furniture

        traffic_furniture = selector.get_furniture_for_zone("traffic", "bedroom")
        assert len(traffic_furniture) == 0


class TestFurnitureSelectorEdgeCases:
    """Tests for FurnitureSelector edge cases."""

    @pytest.fixture
    def mock_tool(self) -> MockFurnitureDbTool:
        """Create mock furniture tool."""
        return MockFurnitureDbTool()

    @pytest.fixture
    def selector(self, mock_tool: MockFurnitureDbTool) -> FurnitureSelector:
        """Create furniture selector instance."""
        return FurnitureSelector(furniture_tool=mock_tool)

    @pytest.mark.asyncio
    async def test_unknown_room_type(self, selector: FurnitureSelector) -> None:
        """Test handling unknown room type."""
        result = await selector.select_furniture(
            room_type="bathroom",  # Not in our mapping
            usable_area=10.0,
        )
        # Should not crash, should have warnings
        assert result is not None
        assert len(result.warnings) > 0

    @pytest.mark.asyncio
    async def test_very_small_area(self, selector: FurnitureSelector) -> None:
        """Test handling very small area."""
        result = await selector.select_furniture(
            room_type="bedroom",
            usable_area=1.0,  # Extremely small
        )
        # May skip items but shouldn't crash
        assert result is not None
