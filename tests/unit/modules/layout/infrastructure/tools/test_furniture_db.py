"""Tests for furniture database tool."""

import pytest

from src.modules.layout.infrastructure.tools.furniture_catalog_data import (
    FURNITURE_CATALOG,
    BudgetLevel,
    CatalogFurniture,
    FurnitureCategory,
    get_essential_furniture,
    get_furniture_by_budget,
    get_furniture_by_category,
    get_furniture_by_id,
    get_furniture_by_room_type,
)
from src.modules.layout.infrastructure.tools.furniture_db_tool import (
    FurnitureSearchInput,
    FurnitureSearchOutput,
    FurnitureSearchResult,
    InMemoryFurnitureDbTool,
)


class TestFurnitureCatalogData:
    """Tests for furniture catalog data module."""

    def test_catalog_exists(self) -> None:
        """Test that catalog has furniture."""
        assert len(FURNITURE_CATALOG) > 0

    def test_furniture_structure(self) -> None:
        """Test that furniture items have required fields."""
        for f in FURNITURE_CATALOG:
            assert f.id
            assert f.name
            assert f.category
            assert f.width > 0
            assert f.depth > 0
            assert f.height > 0
            assert f.budget_level
            assert len(f.room_types) > 0

    def test_categories_covered(self) -> None:
        """Test that main categories have furniture."""
        categories = {f.category for f in FURNITURE_CATALOG}
        assert FurnitureCategory.BED in categories
        assert FurnitureCategory.SOFA in categories
        assert FurnitureCategory.DESK in categories
        assert FurnitureCategory.DINING_TABLE in categories

    def test_get_furniture_by_room_type(self) -> None:
        """Test filtering by room type."""
        bedroom_furniture = get_furniture_by_room_type("bedroom")
        assert len(bedroom_furniture) > 0
        # Check that bedroom has beds
        categories = {f.category for f in bedroom_furniture}
        assert FurnitureCategory.BED in categories

    def test_get_furniture_by_category(self) -> None:
        """Test filtering by category."""
        beds = get_furniture_by_category(FurnitureCategory.BED)
        assert len(beds) > 0
        assert all(f.category == FurnitureCategory.BED for f in beds)

    def test_get_furniture_by_budget(self) -> None:
        """Test filtering by budget."""
        low_budget = get_furniture_by_budget(BudgetLevel.LOW)
        assert len(low_budget) > 0
        assert all(f.budget_level == BudgetLevel.LOW for f in low_budget)

    def test_get_essential_furniture(self) -> None:
        """Test getting essential furniture."""
        bedroom_essentials = get_essential_furniture("bedroom")
        assert len(bedroom_essentials) > 0
        assert all(f.is_essential for f in bedroom_essentials)
        # Bed should be essential
        categories = {f.category for f in bedroom_essentials}
        assert FurnitureCategory.BED in categories

    def test_get_furniture_by_id(self) -> None:
        """Test getting furniture by ID."""
        bed = get_furniture_by_id("bed_queen_001")
        assert bed is not None
        assert bed.category == FurnitureCategory.BED

    def test_get_furniture_by_id_not_found(self) -> None:
        """Test getting non-existent furniture."""
        result = get_furniture_by_id("nonexistent_id")
        assert result is None


class TestCatalogFurniture:
    """Tests for CatalogFurniture dataclass."""

    def test_floor_area(self) -> None:
        """Test floor area calculation."""
        furniture = CatalogFurniture(
            id="test",
            name="Test",
            category=FurnitureCategory.BED,
            width=2.0,
            depth=1.5,
            height=0.5,
            budget_level=BudgetLevel.MEDIUM,
            room_types=("bedroom",),
        )
        assert furniture.floor_area == 3.0  # 2.0 * 1.5

    def test_total_footprint(self) -> None:
        """Test total footprint calculation."""
        furniture = CatalogFurniture(
            id="test",
            name="Test",
            category=FurnitureCategory.BED,
            width=2.0,
            depth=1.5,
            height=0.5,
            budget_level=BudgetLevel.MEDIUM,
            room_types=("bedroom",),
            clearance_front=0.6,
            clearance_sides=0.3,
        )
        # Total width = 2.0 + (0.3 * 2) = 2.6
        # Total depth = 1.5 + 0.6 + 0.3 = 2.4
        # Footprint = 2.6 * 2.4 = 6.24
        assert furniture.total_footprint == pytest.approx(6.24)


class TestFurnitureSearchResult:
    """Tests for FurnitureSearchResult dataclass."""

    def test_from_catalog(self) -> None:
        """Test creating result from catalog furniture."""
        catalog_item = CatalogFurniture(
            id="test_001",
            name="Test Item",
            category=FurnitureCategory.BED,
            width=1.6,
            depth=2.0,
            height=0.5,
            budget_level=BudgetLevel.MEDIUM,
            room_types=("bedroom",),
            is_essential=True,
            feng_shui_element="wood",
            placement_notes="Test notes",
        )
        result = FurnitureSearchResult.from_catalog(catalog_item)

        assert result.id == "test_001"
        assert result.name == "Test Item"
        assert result.category == "bed"
        assert result.width == 1.6
        assert result.is_essential is True

    def test_to_dict(self) -> None:
        """Test result serialization."""
        result = FurnitureSearchResult(
            id="test",
            name="Test",
            category="bed",
            width=1.6,
            depth=2.0,
            height=0.5,
            budget_level="medium",
            is_essential=True,
            clearance_front=0.6,
            clearance_sides=0.3,
            feng_shui_element="wood",
            placement_notes="Notes",
            total_footprint=5.0,
        )
        d = result.to_dict()
        assert d["id"] == "test"
        assert d["is_essential"] is True


class TestFurnitureSearchOutput:
    """Tests for FurnitureSearchOutput dataclass."""

    @pytest.fixture
    def sample_output(self) -> FurnitureSearchOutput:
        """Create sample output for testing."""
        results = [
            FurnitureSearchResult(
                id="bed_001",
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
                total_footprint=5.0,
            ),
            FurnitureSearchResult(
                id="nightstand_001",
                name="Nightstand",
                category="nightstand",
                width=0.45,
                depth=0.4,
                height=0.55,
                budget_level="low",
                is_essential=False,
                clearance_front=0.3,
                clearance_sides=0.1,
                feng_shui_element="wood",
                placement_notes="",
                total_footprint=1.0,
            ),
        ]
        return FurnitureSearchOutput(
            results=results,
            total_matches=2,
            essential_count=1,
            categories_found=["bed", "nightstand"],
        )

    def test_has_results(self, sample_output: FurnitureSearchOutput) -> None:
        """Test has_results property."""
        assert sample_output.has_results is True

        empty_output = FurnitureSearchOutput(
            results=[],
            total_matches=0,
            essential_count=0,
            categories_found=[],
        )
        assert empty_output.has_results is False

    def test_get_by_category(self, sample_output: FurnitureSearchOutput) -> None:
        """Test filtering by category."""
        beds = sample_output.get_by_category("bed")
        assert len(beds) == 1
        assert beds[0].id == "bed_001"

    def test_get_essential_items(self, sample_output: FurnitureSearchOutput) -> None:
        """Test getting essential items."""
        essentials = sample_output.get_essential_items()
        assert len(essentials) == 1
        assert essentials[0].is_essential is True


class TestInMemoryFurnitureDbTool:
    """Tests for InMemoryFurnitureDbTool."""

    @pytest.fixture
    def tool(self) -> InMemoryFurnitureDbTool:
        """Create furniture DB tool instance."""
        return InMemoryFurnitureDbTool()

    def test_tool_name(self, tool: InMemoryFurnitureDbTool) -> None:
        """Test tool name property."""
        assert tool.name == "FURNITURE_DB"

    def test_tool_description(self, tool: InMemoryFurnitureDbTool) -> None:
        """Test tool description property."""
        assert "furniture" in tool.description.lower()
        assert "catalog" in tool.description.lower()

    def test_validate_input_valid(self, tool: InMemoryFurnitureDbTool) -> None:
        """Test validation with valid input."""
        input_data = FurnitureSearchInput(room_type="bedroom")
        errors = tool.validate_input(input_data)
        assert errors == []

    def test_validate_input_invalid_room_type(self, tool: InMemoryFurnitureDbTool) -> None:
        """Test validation with invalid room type."""
        input_data = FurnitureSearchInput(room_type="invalid_room")
        errors = tool.validate_input(input_data)
        assert len(errors) > 0
        assert any("room_type" in e.lower() for e in errors)

    def test_validate_input_negative_dimension(self, tool: InMemoryFurnitureDbTool) -> None:
        """Test validation with negative dimension."""
        input_data = FurnitureSearchInput(room_type="bedroom", min_width=-1.0)
        errors = tool.validate_input(input_data)
        assert len(errors) > 0

    @pytest.mark.asyncio
    async def test_basic_search(self, tool: InMemoryFurnitureDbTool) -> None:
        """Test basic search functionality."""
        input_data = FurnitureSearchInput(room_type="bedroom")
        result = await tool.execute(input_data)

        assert result.success is True
        assert result.data is not None
        assert result.data.has_results is True

    @pytest.mark.asyncio
    async def test_search_bedroom_has_beds(self, tool: InMemoryFurnitureDbTool) -> None:
        """Test that bedroom search includes beds."""
        input_data = FurnitureSearchInput(room_type="bedroom")
        result = await tool.execute(input_data)

        assert result.success is True
        assert "bed" in result.data.categories_found

    @pytest.mark.asyncio
    async def test_search_with_category_filter(self, tool: InMemoryFurnitureDbTool) -> None:
        """Test search with category filter."""
        input_data = FurnitureSearchInput(
            room_type="bedroom",
            categories=[FurnitureCategory.BED],
        )
        result = await tool.execute(input_data)

        assert result.success is True
        assert all(r.category == "bed" for r in result.data.results)

    @pytest.mark.asyncio
    async def test_search_with_budget_filter(self, tool: InMemoryFurnitureDbTool) -> None:
        """Test search with budget filter."""
        input_data = FurnitureSearchInput(
            room_type="bedroom",
            budget_level=BudgetLevel.LOW,
        )
        result = await tool.execute(input_data)

        assert result.success is True
        assert all(r.budget_level == "low" for r in result.data.results)

    @pytest.mark.asyncio
    async def test_search_essential_only(self, tool: InMemoryFurnitureDbTool) -> None:
        """Test search for essential furniture only."""
        input_data = FurnitureSearchInput(
            room_type="bedroom",
            essential_only=True,
        )
        result = await tool.execute(input_data)

        assert result.success is True
        assert all(r.is_essential for r in result.data.results)

    @pytest.mark.asyncio
    async def test_search_with_dimension_filters(self, tool: InMemoryFurnitureDbTool) -> None:
        """Test search with dimension filters."""
        input_data = FurnitureSearchInput(
            room_type="bedroom",
            max_width=1.0,
        )
        result = await tool.execute(input_data)

        assert result.success is True
        assert all(r.width <= 1.0 for r in result.data.results)

    @pytest.mark.asyncio
    async def test_search_max_results(self, tool: InMemoryFurnitureDbTool) -> None:
        """Test that max_results is respected."""
        input_data = FurnitureSearchInput(
            room_type="bedroom",
            max_results=3,
        )
        result = await tool.execute(input_data)

        assert result.success is True
        assert len(result.data.results) <= 3

    @pytest.mark.asyncio
    async def test_search_living_room(self, tool: InMemoryFurnitureDbTool) -> None:
        """Test search for living room furniture."""
        input_data = FurnitureSearchInput(room_type="living_room")
        result = await tool.execute(input_data)

        assert result.success is True
        assert "sofa" in result.data.categories_found

    @pytest.mark.asyncio
    async def test_search_office(self, tool: InMemoryFurnitureDbTool) -> None:
        """Test search for office furniture."""
        input_data = FurnitureSearchInput(room_type="office")
        result = await tool.execute(input_data)

        assert result.success is True
        assert "desk" in result.data.categories_found

    @pytest.mark.asyncio
    async def test_search_dining_room(self, tool: InMemoryFurnitureDbTool) -> None:
        """Test search for dining room furniture."""
        input_data = FurnitureSearchInput(room_type="dining_room")
        result = await tool.execute(input_data)

        assert result.success is True
        assert "dining_table" in result.data.categories_found

    @pytest.mark.asyncio
    async def test_search_returns_metadata(self, tool: InMemoryFurnitureDbTool) -> None:
        """Test that search returns metadata."""
        input_data = FurnitureSearchInput(room_type="bedroom")
        result = await tool.execute(input_data)

        assert result.success is True
        assert "room_type" in result.metadata
        assert "total_matches" in result.metadata
        assert "essential_count" in result.metadata

    @pytest.mark.asyncio
    async def test_search_measures_time(self, tool: InMemoryFurnitureDbTool) -> None:
        """Test that execution time is measured."""
        input_data = FurnitureSearchInput(room_type="bedroom")
        result = await tool.execute(input_data)

        assert result.success is True
        assert result.execution_time_ms >= 0

    @pytest.mark.asyncio
    async def test_results_sorted_essential_first(self, tool: InMemoryFurnitureDbTool) -> None:
        """Test that results have essential items first."""
        input_data = FurnitureSearchInput(room_type="bedroom")
        result = await tool.execute(input_data)

        assert result.success is True
        if len(result.data.results) > 1:
            # Find first non-essential
            first_non_essential_idx = None
            for i, r in enumerate(result.data.results):
                if not r.is_essential:
                    first_non_essential_idx = i
                    break

            # Check no essentials after first non-essential
            if first_non_essential_idx is not None:
                for r in result.data.results[first_non_essential_idx:]:
                    assert not r.is_essential

    def test_get_furniture_by_id(self, tool: InMemoryFurnitureDbTool) -> None:
        """Test getting furniture by ID."""
        furniture = tool.get_furniture_by_id("bed_queen_001")
        assert furniture is not None
        assert furniture.category == FurnitureCategory.BED

    def test_get_all_categories(self, tool: InMemoryFurnitureDbTool) -> None:
        """Test getting all categories."""
        categories = tool.get_all_categories()
        assert len(categories) > 0
        assert "bed" in categories
        assert "sofa" in categories

    def test_get_catalog_size(self, tool: InMemoryFurnitureDbTool) -> None:
        """Test getting catalog size."""
        size = tool.get_catalog_size()
        assert size > 0
        assert size == len(FURNITURE_CATALOG)

    def test_to_langchain_tool_schema(self, tool: InMemoryFurnitureDbTool) -> None:
        """Test LangChain tool schema conversion."""
        schema = tool.to_langchain_tool_schema()

        assert schema["name"] == "FURNITURE_DB"
        assert "parameters" in schema
        assert "room_type" in schema["parameters"]["properties"]
        assert "categories" in schema["parameters"]["properties"]


class TestRoomTypeEssentials:
    """Tests for essential furniture by room type."""

    @pytest.fixture
    def tool(self) -> InMemoryFurnitureDbTool:
        """Create tool instance."""
        return InMemoryFurnitureDbTool()

    @pytest.mark.asyncio
    async def test_bedroom_essentials(self, tool: InMemoryFurnitureDbTool) -> None:
        """Test bedroom has essential bed and wardrobe."""
        input_data = FurnitureSearchInput(room_type="bedroom", essential_only=True)
        result = await tool.execute(input_data)

        categories = {r.category for r in result.data.results}
        assert "bed" in categories
        assert "wardrobe" in categories

    @pytest.mark.asyncio
    async def test_living_room_essentials(self, tool: InMemoryFurnitureDbTool) -> None:
        """Test living room has essential sofa and coffee table."""
        input_data = FurnitureSearchInput(room_type="living_room", essential_only=True)
        result = await tool.execute(input_data)

        categories = {r.category for r in result.data.results}
        assert "sofa" in categories
        assert "coffee_table" in categories

    @pytest.mark.asyncio
    async def test_office_essentials(self, tool: InMemoryFurnitureDbTool) -> None:
        """Test office has essential desk and chair."""
        input_data = FurnitureSearchInput(room_type="office", essential_only=True)
        result = await tool.execute(input_data)

        categories = {r.category for r in result.data.results}
        assert "desk" in categories
        assert "chair" in categories

    @pytest.mark.asyncio
    async def test_dining_room_essentials(self, tool: InMemoryFurnitureDbTool) -> None:
        """Test dining room has essential table and chairs."""
        input_data = FurnitureSearchInput(room_type="dining_room", essential_only=True)
        result = await tool.execute(input_data)

        categories = {r.category for r in result.data.results}
        assert "dining_table" in categories
        assert "dining_chair" in categories
