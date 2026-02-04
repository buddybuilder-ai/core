"""LangChain tools wrapper for feng shui layout generation."""

from __future__ import annotations

from typing import Any, Type

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from src.modules.layout.application.dtos import AgentContext, PlacedFurniture
from src.modules.layout.application.dtos.spatial_analysis import SpatialAnalysisResult
from src.modules.layout.application.services import (
    FengShuiScorer,
    FurnitureSelector,
    InputAnalyzer,
    OutputBuilder,
    PlacementEngine,
    SpatialAnalyzer,
)
from src.modules.layout.domain.entities import Room
from src.modules.layout.infrastructure.tools import InMemoryFurnitureDbTool


# Input schemas for LangChain tools
class AnalyzeRoomInput(BaseModel):
    """Input schema for room analysis tool."""

    room_type: str = Field(description="Type of room (bedroom, living_room, office)")
    width: float = Field(description="Room width in meters")
    depth: float = Field(description="Room depth in meters")
    height: float = Field(default=2.8, description="Room height in meters")


class SelectFurnitureInput(BaseModel):
    """Input schema for furniture selection tool."""

    room_type: str = Field(description="Type of room")
    usable_area: float = Field(description="Available floor area in square meters")
    budget_level: str = Field(default="medium", description="Budget level (low, medium, high)")
    max_items: int = Field(default=10, description="Maximum number of items to select")


class PlaceFurnitureInput(BaseModel):
    """Input schema for furniture placement tool."""

    room_width: float = Field(description="Room width in meters")
    room_depth: float = Field(description="Room depth in meters")


class ScoreLayoutInput(BaseModel):
    """Input schema for layout scoring tool."""

    pass  # Uses context from agent


class GenerateOutputInput(BaseModel):
    """Input schema for output generation tool."""

    pass  # Uses context from agent


class AnalyzeRoomTool(BaseTool):
    """LangChain tool for analyzing room spatial characteristics."""

    name: str = "analyze_room"
    description: str = (
        "Analyzes a room's spatial characteristics including dimensions, "
        "door/window positions, command positions, and traffic flow. "
        "Use this to understand the room layout before placing furniture."
    )
    args_schema: Type[BaseModel] = AnalyzeRoomInput

    _spatial_analyzer: SpatialAnalyzer | None = None
    _input_analyzer: InputAnalyzer | None = None

    def __init__(self, **kwargs: Any) -> None:
        """Initialize the tool."""
        super().__init__(**kwargs)
        self._spatial_analyzer = SpatialAnalyzer()
        self._input_analyzer = InputAnalyzer()

    def _run(
        self,
        room_type: str,
        width: float,
        depth: float,
        height: float = 2.8,
    ) -> dict[str, Any]:
        """Run the room analysis.

        Args:
            room_type: Type of room.
            width: Room width in meters.
            depth: Room depth in meters.
            height: Room height in meters.

        Returns:
            Dictionary with analysis results.
        """
        from src.modules.layout.domain.entities import RoomType

        # Map room type string to enum
        room_type_map = {
            "bedroom": RoomType.BEDROOM,
            "living_room": RoomType.LIVING_ROOM,
            "office": RoomType.OFFICE,
            "dining_room": RoomType.DINING_ROOM,
        }
        room_type_enum = room_type_map.get(room_type, RoomType.BEDROOM)

        # Create room directly
        room = Room(
            width=width,
            depth=depth,
            height=height,
            room_type=room_type_enum,
        )

        # Analyze spatial characteristics
        analysis = self._spatial_analyzer.analyze(room)

        return {
            "room_area": analysis.room_area,
            "usable_area": analysis.usable_area,
            "usable_ratio": analysis.usable_ratio,
            "command_positions": [p.to_dict() for p in analysis.command_positions],
            "zone_count": len(analysis.zones),
            "recommendations": analysis.feng_shui_recommendations,
        }

    async def _arun(
        self,
        room_type: str,
        width: float,
        depth: float,
        height: float = 2.8,
    ) -> dict[str, Any]:
        """Async run - delegates to sync implementation."""
        return self._run(room_type, width, depth, height)


class SelectFurnitureTool(BaseTool):
    """LangChain tool for selecting appropriate furniture."""

    name: str = "select_furniture"
    description: str = (
        "Selects appropriate furniture items for a room based on room type, "
        "available space, and budget. Returns a prioritized list of furniture "
        "with feng shui placement notes."
    )
    args_schema: Type[BaseModel] = SelectFurnitureInput

    _furniture_selector: FurnitureSelector | None = None
    _furniture_tool: InMemoryFurnitureDbTool | None = None

    def __init__(self, **kwargs: Any) -> None:
        """Initialize the tool."""
        super().__init__(**kwargs)
        self._furniture_tool = InMemoryFurnitureDbTool()
        self._furniture_selector = FurnitureSelector(self._furniture_tool)

    def _run(
        self,
        room_type: str,
        usable_area: float,
        budget_level: str = "medium",
        max_items: int = 10,
    ) -> dict[str, Any]:
        """Run furniture selection synchronously."""
        import asyncio

        # Run async method synchronously
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(
                self._arun(room_type, usable_area, budget_level, max_items)
            )
        finally:
            loop.close()

    async def _arun(
        self,
        room_type: str,
        usable_area: float,
        budget_level: str = "medium",
        max_items: int = 10,
    ) -> dict[str, Any]:
        """Run furniture selection.

        Args:
            room_type: Type of room.
            usable_area: Available floor area.
            budget_level: Budget level.
            max_items: Maximum items to select.

        Returns:
            Dictionary with selected furniture.
        """
        from src.modules.layout.application.dtos import UserPreferences

        preferences = UserPreferences(budget_level=budget_level)

        result = await self._furniture_selector.select_furniture(
            room_type=room_type,
            usable_area=usable_area,
            preferences=preferences,
            max_items=max_items,
        )

        return {
            "selected_count": len(result.selections),
            "essential_count": result.essential_count,
            "optional_count": result.optional_count,
            "total_area_needed": result.total_area_needed,
            "furniture": [s.to_dict() for s in result.get_by_priority()],
            "warnings": result.warnings,
        }


class PlaceFurnitureTool(BaseTool):
    """LangChain tool for placing furniture in a room."""

    name: str = "place_furniture"
    description: str = (
        "Places furniture items in a room using grid-based placement with "
        "feng shui optimization. Handles collision detection and fallback "
        "strategies automatically."
    )
    args_schema: Type[BaseModel] = PlaceFurnitureInput

    _context: AgentContext | None = None
    _selections: list[Any] | None = None

    def set_context(
        self,
        context: AgentContext,
        selections: list[Any],
    ) -> None:
        """Set the agent context and furniture selections.

        Args:
            context: Agent context.
            selections: Furniture selections to place.
        """
        self._context = context
        self._selections = selections

    def _run(
        self,
        room_width: float,
        room_depth: float,
    ) -> dict[str, Any]:
        """Run furniture placement.

        Args:
            room_width: Room width in meters.
            room_depth: Room depth in meters.

        Returns:
            Dictionary with placement results.
        """
        if not self._selections:
            return {
                "success": False,
                "error": "No furniture selections provided",
            }

        engine = PlacementEngine(room_width=room_width, room_depth=room_depth)

        # Get spatial analysis if available
        spatial_analysis = None
        if self._context and "spatial_analysis" in self._context.metadata:
            spatial_analysis = self._context.metadata.get("spatial_analysis")

        result = engine.place_all(self._selections, spatial_analysis)

        return {
            "success": result.overall_status.value == "success",
            "placed_count": result.placed_count,
            "failed_count": result.failed_count,
            "success_rate": result.success_rate,
            "furniture": [
                {
                    "id": f.id,
                    "name": f.name,
                    "category": f.category,
                    "position": {"x": f.pos_x, "z": f.pos_z},
                    "rotation": f.rotation,
                }
                for f in result.get_placed_furniture()
            ],
            "execution_time_ms": result.execution_time_ms,
        }

    async def _arun(
        self,
        room_width: float,
        room_depth: float,
    ) -> dict[str, Any]:
        """Async run - delegates to sync implementation."""
        return self._run(room_width, room_depth)


class ScoreLayoutTool(BaseTool):
    """LangChain tool for scoring a layout's feng shui quality."""

    name: str = "score_layout"
    description: str = (
        "Scores a furniture layout based on feng shui principles including "
        "command position, five elements balance, chi flow, and sha chi avoidance. "
        "Returns a score from 0-100 with improvement recommendations."
    )
    args_schema: Type[BaseModel] = ScoreLayoutInput

    _context: AgentContext | None = None
    _placed_furniture: list[PlacedFurniture] | None = None

    def set_context(
        self,
        context: AgentContext,
        placed_furniture: list[PlacedFurniture] | None = None,
    ) -> None:
        """Set the agent context.

        Args:
            context: Agent context.
            placed_furniture: Placed furniture list.
        """
        self._context = context
        self._placed_furniture = placed_furniture or context.placed_furniture

    def _run(self) -> dict[str, Any]:
        """Run layout scoring.

        Returns:
            Dictionary with scoring results.
        """
        if not self._context:
            return {
                "success": False,
                "error": "No context provided",
            }

        scorer = FengShuiScorer()
        result = scorer.score_layout(
            room=self._context.room,
            placed_furniture=self._placed_furniture or [],
        )

        return {
            "success": True,
            "total_score": result.score.total,
            "grade": result.score.grade,
            "is_acceptable": result.score.is_acceptable,
            "breakdown": {
                "command_position": result.score.command_position,
                "five_elements": result.score.five_elements,
                "chi_flow": result.score.chi_flow,
                "sha_chi_avoidance": result.score.sha_chi_avoidance,
            },
            "weakest_component": result.score.get_weakest_component(),
            "recommendations": result.recommendations,
        }

    async def _arun(self) -> dict[str, Any]:
        """Async run - delegates to sync implementation."""
        return self._run()


class GenerateOutputTool(BaseTool):
    """LangChain tool for generating final layout output."""

    name: str = "generate_output"
    description: str = (
        "Generates the final layout output including furniture positions, "
        "feng shui score, recommendations, and metadata. Call this after "
        "placement and scoring are complete."
    )
    args_schema: Type[BaseModel] = GenerateOutputInput

    _context: AgentContext | None = None

    def set_context(self, context: AgentContext) -> None:
        """Set the agent context.

        Args:
            context: Agent context.
        """
        self._context = context

    def _run(self) -> dict[str, Any]:
        """Run output generation.

        Returns:
            Dictionary with layout output.
        """
        if not self._context:
            return {
                "success": False,
                "error": "No context provided",
            }

        builder = OutputBuilder()
        output = builder.build_from_context(self._context)

        return {
            "success": True,
            "room_type": output.room_type,
            "feng_shui_score": output.feng_shui_score,
            "furniture_count": len(output.furniture),
            "output": builder.format_as_simple_json(output),
        }

    async def _arun(self) -> dict[str, Any]:
        """Async run - delegates to sync implementation."""
        return self._run()


def create_layout_tools() -> list[BaseTool]:
    """Create all layout generation tools.

    Returns:
        List of LangChain tools for layout generation.
    """
    return [
        AnalyzeRoomTool(),
        SelectFurnitureTool(),
        PlaceFurnitureTool(),
        ScoreLayoutTool(),
        GenerateOutputTool(),
    ]


def get_tool_descriptions() -> dict[str, str]:
    """Get descriptions of all layout tools.

    Returns:
        Dictionary mapping tool names to descriptions.
    """
    tools = create_layout_tools()
    return {tool.name: tool.description for tool in tools}
