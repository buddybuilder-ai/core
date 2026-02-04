"""Tests for LangChain tools wrapper."""

import pytest

from src.modules.layout.application.agent.langchain_tools import (
    AnalyzeRoomTool,
    GenerateOutputTool,
    PlaceFurnitureTool,
    ScoreLayoutTool,
    SelectFurnitureTool,
    create_layout_tools,
    get_tool_descriptions,
)
from src.modules.layout.application.dtos import AgentContext, PlacedFurniture
from src.modules.layout.application.services.furniture_selector import FurnitureSelection
from src.modules.layout.domain.entities import Room, RoomType
from src.modules.layout.domain.value_objects import FengShuiScore
from src.modules.layout.infrastructure.tools import FurnitureSearchResult


class TestAnalyzeRoomTool:
    """Tests for AnalyzeRoomTool."""

    @pytest.fixture
    def tool(self) -> AnalyzeRoomTool:
        """Create test tool."""
        return AnalyzeRoomTool()

    def test_tool_name(self, tool: AnalyzeRoomTool) -> None:
        """Test tool name."""
        assert tool.name == "analyze_room"

    def test_tool_description(self, tool: AnalyzeRoomTool) -> None:
        """Test tool has description."""
        assert len(tool.description) > 0
        assert "room" in tool.description.lower()

    def test_analyze_bedroom(self, tool: AnalyzeRoomTool) -> None:
        """Test analyzing a bedroom."""
        result = tool._run(
            room_type="bedroom",
            width=5.0,
            depth=4.0,
            height=2.8,
        )

        assert "room_area" in result
        assert result["room_area"] == 20.0
        assert "usable_area" in result
        assert "command_positions" in result
        assert "recommendations" in result

    def test_analyze_office(self, tool: AnalyzeRoomTool) -> None:
        """Test analyzing an office."""
        result = tool._run(
            room_type="office",
            width=4.0,
            depth=3.0,
        )

        assert result["room_area"] == 12.0

    def test_analyze_living_room(self, tool: AnalyzeRoomTool) -> None:
        """Test analyzing a living room."""
        result = tool._run(
            room_type="living_room",
            width=6.0,
            depth=5.0,
        )

        assert result["room_area"] == 30.0


class TestSelectFurnitureTool:
    """Tests for SelectFurnitureTool."""

    @pytest.fixture
    def tool(self) -> SelectFurnitureTool:
        """Create test tool."""
        return SelectFurnitureTool()

    def test_tool_name(self, tool: SelectFurnitureTool) -> None:
        """Test tool name."""
        assert tool.name == "select_furniture"

    def test_tool_description(self, tool: SelectFurnitureTool) -> None:
        """Test tool has description."""
        assert len(tool.description) > 0
        assert "furniture" in tool.description.lower()

    @pytest.mark.asyncio
    async def test_select_furniture_bedroom(self, tool: SelectFurnitureTool) -> None:
        """Test selecting furniture for bedroom."""
        result = await tool._arun(
            room_type="bedroom",
            usable_area=15.0,
            budget_level="medium",
            max_items=5,
        )

        assert "selected_count" in result
        assert "essential_count" in result
        assert "furniture" in result
        assert result["selected_count"] > 0

    @pytest.mark.asyncio
    async def test_select_furniture_office(self, tool: SelectFurnitureTool) -> None:
        """Test selecting furniture for office."""
        result = await tool._arun(
            room_type="office",
            usable_area=10.0,
            budget_level="low",
            max_items=3,
        )

        assert result["selected_count"] > 0


class TestPlaceFurnitureTool:
    """Tests for PlaceFurnitureTool."""

    @pytest.fixture
    def tool(self) -> PlaceFurnitureTool:
        """Create test tool."""
        return PlaceFurnitureTool()

    @pytest.fixture
    def selections(self) -> list[FurnitureSelection]:
        """Create test selections."""
        item = FurnitureSearchResult(
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
        return [
            FurnitureSelection(
                item=item,
                priority=1,
                is_essential=True,
            )
        ]

    def test_tool_name(self, tool: PlaceFurnitureTool) -> None:
        """Test tool name."""
        assert tool.name == "place_furniture"

    def test_tool_description(self, tool: PlaceFurnitureTool) -> None:
        """Test tool has description."""
        assert len(tool.description) > 0
        assert "furniture" in tool.description.lower()

    def test_place_without_selections(self, tool: PlaceFurnitureTool) -> None:
        """Test placing without selections returns error."""
        result = tool._run(room_width=5.0, room_depth=4.0)

        assert result["success"] is False
        assert "error" in result

    def test_place_with_selections(
        self,
        tool: PlaceFurnitureTool,
        selections: list[FurnitureSelection],
    ) -> None:
        """Test placing with selections."""
        room = Room(width=5.0, depth=4.0, height=2.8, room_type=RoomType.BEDROOM)
        context = AgentContext(room=room, room_type="bedroom")

        tool.set_context(context, selections)
        result = tool._run(room_width=5.0, room_depth=4.0)

        assert result["success"] is True
        assert result["placed_count"] == 1
        assert len(result["furniture"]) == 1


class TestScoreLayoutTool:
    """Tests for ScoreLayoutTool."""

    @pytest.fixture
    def tool(self) -> ScoreLayoutTool:
        """Create test tool."""
        return ScoreLayoutTool()

    @pytest.fixture
    def context_with_furniture(self) -> AgentContext:
        """Create context with placed furniture."""
        room = Room(width=5.0, depth=4.0, height=2.8, room_type=RoomType.BEDROOM)
        context = AgentContext(room=room, room_type="bedroom")
        context.placed_furniture = [
            PlacedFurniture(
                id="bed_1",
                furniture_id="bed_001",
                name="Bed",
                category="bed",
                pos_x=1.5,
                pos_z=0.3,
                width=1.6,
                depth=2.0,
                height=0.5,
                rotation=0,
                is_essential=True,
            )
        ]
        return context

    def test_tool_name(self, tool: ScoreLayoutTool) -> None:
        """Test tool name."""
        assert tool.name == "score_layout"

    def test_tool_description(self, tool: ScoreLayoutTool) -> None:
        """Test tool has description."""
        assert len(tool.description) > 0
        assert "feng shui" in tool.description.lower()

    def test_score_without_context(self, tool: ScoreLayoutTool) -> None:
        """Test scoring without context returns error."""
        result = tool._run()

        assert result["success"] is False
        assert "error" in result

    def test_score_with_context(
        self,
        tool: ScoreLayoutTool,
        context_with_furniture: AgentContext,
    ) -> None:
        """Test scoring with context."""
        tool.set_context(context_with_furniture)
        result = tool._run()

        assert result["success"] is True
        assert "total_score" in result
        assert "grade" in result
        assert "breakdown" in result
        assert 0 <= result["total_score"] <= 100


class TestGenerateOutputTool:
    """Tests for GenerateOutputTool."""

    @pytest.fixture
    def tool(self) -> GenerateOutputTool:
        """Create test tool."""
        return GenerateOutputTool()

    @pytest.fixture
    def context_with_score(self) -> AgentContext:
        """Create context with furniture and score."""
        room = Room(width=5.0, depth=4.0, height=2.8, room_type=RoomType.BEDROOM)
        context = AgentContext(room=room, room_type="bedroom")
        context.placed_furniture = [
            PlacedFurniture(
                id="bed_1",
                furniture_id="bed_001",
                name="Bed",
                category="bed",
                pos_x=1.5,
                pos_z=0.3,
                width=1.6,
                depth=2.0,
                height=0.5,
                rotation=0,
                is_essential=True,
            )
        ]
        context.feng_shui_score = FengShuiScore(
            command_position=25,
            five_elements=15,
            chi_flow=20,
            sha_chi_avoidance=20,
        )
        return context

    def test_tool_name(self, tool: GenerateOutputTool) -> None:
        """Test tool name."""
        assert tool.name == "generate_output"

    def test_tool_description(self, tool: GenerateOutputTool) -> None:
        """Test tool has description."""
        assert len(tool.description) > 0
        assert "output" in tool.description.lower()

    def test_generate_without_context(self, tool: GenerateOutputTool) -> None:
        """Test generating without context returns error."""
        result = tool._run()

        assert result["success"] is False
        assert "error" in result

    def test_generate_with_context(
        self,
        tool: GenerateOutputTool,
        context_with_score: AgentContext,
    ) -> None:
        """Test generating with context."""
        tool.set_context(context_with_score)
        result = tool._run()

        assert result["success"] is True
        assert result["room_type"] == "bedroom"
        assert result["feng_shui_score"] == 80
        assert result["furniture_count"] == 1
        assert "output" in result


class TestCreateLayoutTools:
    """Tests for create_layout_tools function."""

    def test_create_all_tools(self) -> None:
        """Test creating all layout tools."""
        tools = create_layout_tools()

        assert len(tools) == 5
        tool_names = {tool.name for tool in tools}
        assert "analyze_room" in tool_names
        assert "select_furniture" in tool_names
        assert "place_furniture" in tool_names
        assert "score_layout" in tool_names
        assert "generate_output" in tool_names

    def test_tools_have_descriptions(self) -> None:
        """Test all tools have descriptions."""
        tools = create_layout_tools()

        for tool in tools:
            assert len(tool.description) > 0


class TestGetToolDescriptions:
    """Tests for get_tool_descriptions function."""

    def test_get_descriptions(self) -> None:
        """Test getting tool descriptions."""
        descriptions = get_tool_descriptions()

        assert len(descriptions) == 5
        assert "analyze_room" in descriptions
        assert "select_furniture" in descriptions
        assert all(len(desc) > 0 for desc in descriptions.values())


class TestToolIntegration:
    """Integration tests for tool workflow."""

    @pytest.mark.asyncio
    async def test_full_workflow(self) -> None:
        """Test running through full tool workflow."""
        # Step 1: Analyze room
        analyze_tool = AnalyzeRoomTool()
        room_analysis = analyze_tool._run(
            room_type="bedroom",
            width=5.0,
            depth=4.0,
        )
        assert room_analysis["room_area"] == 20.0

        # Step 2: Select furniture
        select_tool = SelectFurnitureTool()
        furniture_result = await select_tool._arun(
            room_type="bedroom",
            usable_area=room_analysis["usable_area"],
            max_items=3,
        )
        assert furniture_result["selected_count"] > 0

        # Step 3: Create context for remaining tools
        room = Room(width=5.0, depth=4.0, height=2.8, room_type=RoomType.BEDROOM)
        context = AgentContext(room=room, room_type="bedroom")

        # Step 4: Score layout (even empty)
        score_tool = ScoreLayoutTool()
        score_tool.set_context(context, [])
        score_result = score_tool._run()
        assert score_result["success"] is True

        # Step 5: Generate output
        output_tool = GenerateOutputTool()
        output_tool.set_context(context)
        output_result = output_tool._run()
        assert output_result["success"] is True
