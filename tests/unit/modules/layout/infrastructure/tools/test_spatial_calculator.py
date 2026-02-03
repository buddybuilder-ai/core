"""Tests for spatial calculator tool."""

import pytest

from src.modules.layout.domain.entities import DoorPosition, Room, RoomType, WallSide, WindowPosition
from src.modules.layout.infrastructure.tools.spatial_calculator_tool import (
    SpatialAnalysisInput,
    SpatialCalculatorTool,
    Zone,
    ZoneType,
)


class TestZone:
    """Tests for Zone dataclass."""

    def test_zone_creation(self) -> None:
        """Test creating a zone."""
        zone = Zone(
            zone_type=ZoneType.CENTER,
            x_min=1.0,
            x_max=4.0,
            z_min=1.0,
            z_max=3.0,
            priority=5,
            notes="Test zone",
        )
        assert zone.zone_type == ZoneType.CENTER
        assert zone.x_min == 1.0
        assert zone.x_max == 4.0

    def test_zone_width(self) -> None:
        """Test zone width calculation."""
        zone = Zone(
            zone_type=ZoneType.CENTER,
            x_min=1.0,
            x_max=4.0,
            z_min=0.0,
            z_max=2.0,
        )
        assert zone.width == 3.0

    def test_zone_depth(self) -> None:
        """Test zone depth calculation."""
        zone = Zone(
            zone_type=ZoneType.CENTER,
            x_min=0.0,
            x_max=3.0,
            z_min=1.0,
            z_max=4.0,
        )
        assert zone.depth == 3.0

    def test_zone_area(self) -> None:
        """Test zone area calculation."""
        zone = Zone(
            zone_type=ZoneType.CENTER,
            x_min=0.0,
            x_max=2.0,
            z_min=0.0,
            z_max=3.0,
        )
        assert zone.area == 6.0

    def test_zone_center(self) -> None:
        """Test zone center calculation."""
        zone = Zone(
            zone_type=ZoneType.CENTER,
            x_min=0.0,
            x_max=4.0,
            z_min=0.0,
            z_max=6.0,
        )
        center = zone.center
        assert center.x == 2.0
        assert center.z == 3.0

    def test_zone_contains_point_inside(self) -> None:
        """Test contains_point with point inside."""
        zone = Zone(
            zone_type=ZoneType.CENTER,
            x_min=0.0,
            x_max=4.0,
            z_min=0.0,
            z_max=4.0,
        )
        assert zone.contains_point(2.0, 2.0) is True

    def test_zone_contains_point_outside(self) -> None:
        """Test contains_point with point outside."""
        zone = Zone(
            zone_type=ZoneType.CENTER,
            x_min=0.0,
            x_max=4.0,
            z_min=0.0,
            z_max=4.0,
        )
        assert zone.contains_point(5.0, 2.0) is False

    def test_zone_contains_point_on_boundary(self) -> None:
        """Test contains_point with point on boundary."""
        zone = Zone(
            zone_type=ZoneType.CENTER,
            x_min=0.0,
            x_max=4.0,
            z_min=0.0,
            z_max=4.0,
        )
        assert zone.contains_point(0.0, 0.0) is True
        assert zone.contains_point(4.0, 4.0) is True

    def test_zone_overlaps_true(self) -> None:
        """Test overlapping zones."""
        zone1 = Zone(
            zone_type=ZoneType.CENTER,
            x_min=0.0,
            x_max=3.0,
            z_min=0.0,
            z_max=3.0,
        )
        zone2 = Zone(
            zone_type=ZoneType.TRAFFIC,
            x_min=2.0,
            x_max=5.0,
            z_min=2.0,
            z_max=5.0,
        )
        assert zone1.overlaps(zone2) is True

    def test_zone_overlaps_false(self) -> None:
        """Test non-overlapping zones."""
        zone1 = Zone(
            zone_type=ZoneType.CENTER,
            x_min=0.0,
            x_max=2.0,
            z_min=0.0,
            z_max=2.0,
        )
        zone2 = Zone(
            zone_type=ZoneType.TRAFFIC,
            x_min=3.0,
            x_max=5.0,
            z_min=3.0,
            z_max=5.0,
        )
        assert zone1.overlaps(zone2) is False

    def test_zone_overlaps_adjacent(self) -> None:
        """Test adjacent zones (touching but not overlapping)."""
        zone1 = Zone(
            zone_type=ZoneType.CENTER,
            x_min=0.0,
            x_max=2.0,
            z_min=0.0,
            z_max=2.0,
        )
        zone2 = Zone(
            zone_type=ZoneType.TRAFFIC,
            x_min=2.0,
            x_max=4.0,
            z_min=0.0,
            z_max=2.0,
        )
        # Adjacent zones should not overlap
        assert zone1.overlaps(zone2) is False


class TestZoneType:
    """Tests for ZoneType enum."""

    def test_zone_types(self) -> None:
        """Test all zone types exist."""
        assert ZoneType.COMMAND.value == "command"
        assert ZoneType.TRAFFIC.value == "traffic"
        assert ZoneType.DOOR_SWING.value == "door_swing"
        assert ZoneType.WINDOW.value == "window"
        assert ZoneType.CORNER.value == "corner"
        assert ZoneType.CENTER.value == "center"
        assert ZoneType.WALL.value == "wall"


class TestSpatialCalculatorTool:
    """Tests for SpatialCalculatorTool."""

    @pytest.fixture
    def tool(self) -> SpatialCalculatorTool:
        """Create spatial calculator tool instance."""
        return SpatialCalculatorTool()

    @pytest.fixture
    def simple_room(self) -> Room:
        """Create a simple room for testing."""
        return Room(
            width=5.0,
            depth=4.0,
            room_type=RoomType.BEDROOM,
            doors=[DoorPosition(wall=WallSide.SOUTH, offset=2.5, width=0.9)],
            windows=[WindowPosition(wall=WallSide.NORTH, offset=2.5, width=1.5)],
        )

    @pytest.fixture
    def complex_room(self) -> Room:
        """Create a room with multiple doors and windows."""
        return Room(
            width=6.0,
            depth=5.0,
            room_type=RoomType.LIVING_ROOM,
            doors=[
                DoorPosition(wall=WallSide.SOUTH, offset=1.5, width=0.9),
                DoorPosition(wall=WallSide.EAST, offset=2.5, width=0.9),
            ],
            windows=[
                WindowPosition(wall=WallSide.NORTH, offset=3.0, width=2.0),
                WindowPosition(wall=WallSide.WEST, offset=2.5, width=1.2),
            ],
        )

    def test_tool_name(self, tool: SpatialCalculatorTool) -> None:
        """Test tool name property."""
        assert tool.name == "SPATIAL_CALCULATOR"

    def test_tool_description(self, tool: SpatialCalculatorTool) -> None:
        """Test tool description property."""
        assert "spatial" in tool.description.lower()
        assert "room" in tool.description.lower()

    def test_validate_input_valid(self, tool: SpatialCalculatorTool, simple_room: Room) -> None:
        """Test validation with valid input."""
        input_data = SpatialAnalysisInput(room=simple_room)
        errors = tool.validate_input(input_data)
        assert errors == []

    def test_room_invalid_dimensions_raises_error(self, tool: SpatialCalculatorTool) -> None:
        """Test that invalid room dimensions raise error at construction."""
        # Room class validates dimensions at construction time
        with pytest.raises(ValueError, match="width must be > 0"):
            Room(width=-1.0, depth=4.0, room_type=RoomType.BEDROOM)

    def test_validate_input_negative_clearance(self, tool: SpatialCalculatorTool, simple_room: Room) -> None:
        """Test validation with negative clearance."""
        input_data = SpatialAnalysisInput(room=simple_room, clearance=-0.5)
        errors = tool.validate_input(input_data)
        assert len(errors) > 0
        assert any("clearance" in e.lower() for e in errors)

    @pytest.mark.asyncio
    async def test_execute_simple_room(self, tool: SpatialCalculatorTool, simple_room: Room) -> None:
        """Test execution with a simple room."""
        input_data = SpatialAnalysisInput(room=simple_room)
        result = await tool.execute(input_data)

        assert result.success is True
        assert result.data is not None
        assert result.data.total_area == 20.0  # 5x4
        assert result.data.usable_area > 0
        assert result.data.usable_area <= result.data.total_area

    @pytest.mark.asyncio
    async def test_execute_identifies_zones(self, tool: SpatialCalculatorTool, simple_room: Room) -> None:
        """Test that execution identifies multiple zones."""
        input_data = SpatialAnalysisInput(room=simple_room)
        result = await tool.execute(input_data)

        assert result.success is True
        assert result.data is not None
        assert len(result.data.zones) > 0

        zone_types = [z.zone_type for z in result.data.zones]
        assert ZoneType.DOOR_SWING in zone_types
        assert ZoneType.WINDOW in zone_types
        assert ZoneType.CORNER in zone_types
        assert ZoneType.CENTER in zone_types

    @pytest.mark.asyncio
    async def test_execute_identifies_command_positions(self, tool: SpatialCalculatorTool, simple_room: Room) -> None:
        """Test that execution identifies command positions."""
        input_data = SpatialAnalysisInput(room=simple_room)
        result = await tool.execute(input_data)

        assert result.success is True
        assert result.data is not None
        assert len(result.data.command_positions) > 0

        # Command positions should be within room bounds
        for pos in result.data.command_positions:
            assert 0 <= pos.x <= simple_room.width
            assert 0 <= pos.z <= simple_room.depth

    @pytest.mark.asyncio
    async def test_execute_identifies_traffic_paths(self, tool: SpatialCalculatorTool, simple_room: Room) -> None:
        """Test that execution identifies traffic paths."""
        input_data = SpatialAnalysisInput(room=simple_room)
        result = await tool.execute(input_data)

        assert result.success is True
        assert result.data is not None
        assert len(result.data.traffic_paths) > 0

        # Traffic paths should have TRAFFIC zone type
        for path in result.data.traffic_paths:
            assert path.zone_type == ZoneType.TRAFFIC

    @pytest.mark.asyncio
    async def test_execute_identifies_blocked_areas(self, tool: SpatialCalculatorTool, simple_room: Room) -> None:
        """Test that execution identifies blocked areas."""
        input_data = SpatialAnalysisInput(room=simple_room)
        result = await tool.execute(input_data)

        assert result.success is True
        assert result.data is not None
        assert len(result.data.blocked_areas) > 0

        # Blocked areas should include door swing zones
        blocked_types = [z.zone_type for z in result.data.blocked_areas]
        assert ZoneType.DOOR_SWING in blocked_types

    @pytest.mark.asyncio
    async def test_execute_complex_room(self, tool: SpatialCalculatorTool, complex_room: Room) -> None:
        """Test execution with complex room."""
        input_data = SpatialAnalysisInput(room=complex_room)
        result = await tool.execute(input_data)

        assert result.success is True
        assert result.data is not None
        assert result.data.total_area == 30.0  # 6x5

        # Should have more zones due to more doors/windows
        door_swing_zones = result.data.get_zones_by_type(ZoneType.DOOR_SWING)
        assert len(door_swing_zones) == 2  # Two doors

        window_zones = result.data.get_zones_by_type(ZoneType.WINDOW)
        assert len(window_zones) == 2  # Two windows

    @pytest.mark.asyncio
    async def test_execute_with_custom_clearance(self, tool: SpatialCalculatorTool, simple_room: Room) -> None:
        """Test execution with custom clearance."""
        input_data = SpatialAnalysisInput(room=simple_room, clearance=0.8)
        result = await tool.execute(input_data)

        assert result.success is True
        assert result.data is not None

    @pytest.mark.asyncio
    async def test_execute_with_custom_door_swing_depth(self, tool: SpatialCalculatorTool, simple_room: Room) -> None:
        """Test execution with custom door swing depth."""
        input_data = SpatialAnalysisInput(room=simple_room, door_swing_depth=1.2)
        result = await tool.execute(input_data)

        assert result.success is True
        assert result.data is not None

        # Door swing zones should be larger
        door_swing_zones = result.data.get_zones_by_type(ZoneType.DOOR_SWING)
        assert len(door_swing_zones) > 0

    @pytest.mark.asyncio
    async def test_execute_returns_metadata(self, tool: SpatialCalculatorTool, simple_room: Room) -> None:
        """Test that execution returns metadata."""
        input_data = SpatialAnalysisInput(room=simple_room)
        result = await tool.execute(input_data)

        assert result.success is True
        assert "room_width" in result.metadata
        assert "room_depth" in result.metadata
        assert "num_doors" in result.metadata
        assert "num_windows" in result.metadata
        assert "num_zones" in result.metadata

    @pytest.mark.asyncio
    async def test_execute_measures_time(self, tool: SpatialCalculatorTool, simple_room: Room) -> None:
        """Test that execution time is measured."""
        input_data = SpatialAnalysisInput(room=simple_room)
        result = await tool.execute(input_data)

        assert result.success is True
        assert result.execution_time_ms >= 0

    @pytest.mark.asyncio
    async def test_safe_execute_with_invalid_clearance(self, tool: SpatialCalculatorTool, simple_room: Room) -> None:
        """Test safe_execute handles validation errors for negative clearance."""
        input_data = SpatialAnalysisInput(room=simple_room, clearance=-0.5)
        result = await tool.safe_execute(input_data)

        assert result.success is False
        assert "validation" in result.error.lower()

    def test_to_langchain_tool_schema(self, tool: SpatialCalculatorTool) -> None:
        """Test LangChain tool schema conversion."""
        schema = tool.to_langchain_tool_schema()

        assert schema["name"] == "SPATIAL_CALCULATOR"
        assert "parameters" in schema
        assert "room_width" in schema["parameters"]["properties"]
        assert "room_depth" in schema["parameters"]["properties"]


class TestSpatialAnalysisOutput:
    """Tests for SpatialAnalysisOutput."""

    @pytest.fixture
    def tool(self) -> SpatialCalculatorTool:
        """Create tool instance."""
        return SpatialCalculatorTool()

    @pytest.fixture
    def simple_room(self) -> Room:
        """Create a simple room."""
        return Room(
            width=5.0,
            depth=4.0,
            room_type=RoomType.BEDROOM,
            doors=[DoorPosition(wall=WallSide.SOUTH, offset=2.5, width=0.9)],
        )

    @pytest.mark.asyncio
    async def test_usable_percentage(self, tool: SpatialCalculatorTool, simple_room: Room) -> None:
        """Test usable percentage calculation."""
        input_data = SpatialAnalysisInput(room=simple_room)
        result = await tool.execute(input_data)

        assert result.success is True
        output = result.data
        assert output is not None
        assert 0 <= output.usable_percentage <= 100

    @pytest.mark.asyncio
    async def test_get_zones_by_type(self, tool: SpatialCalculatorTool, simple_room: Room) -> None:
        """Test filtering zones by type."""
        input_data = SpatialAnalysisInput(room=simple_room)
        result = await tool.execute(input_data)

        assert result.success is True
        output = result.data
        assert output is not None

        corner_zones = output.get_zones_by_type(ZoneType.CORNER)
        assert len(corner_zones) == 4  # Four corners

        center_zones = output.get_zones_by_type(ZoneType.CENTER)
        assert len(center_zones) == 1  # One center


class TestDoorSwingCalculation:
    """Tests for door swing zone calculations."""

    @pytest.fixture
    def tool(self) -> SpatialCalculatorTool:
        """Create tool instance."""
        return SpatialCalculatorTool()

    @pytest.mark.asyncio
    async def test_north_door_swing(self, tool: SpatialCalculatorTool) -> None:
        """Test door swing calculation for north wall door."""
        room = Room(
            width=5.0,
            depth=4.0,
            room_type=RoomType.BEDROOM,
            doors=[DoorPosition(wall=WallSide.NORTH, offset=2.5, width=0.9)],
        )
        input_data = SpatialAnalysisInput(room=room)
        result = await tool.execute(input_data)

        assert result.success is True
        door_swing = result.data.get_zones_by_type(ZoneType.DOOR_SWING)[0]
        assert door_swing.z_min == 0  # Against north wall

    @pytest.mark.asyncio
    async def test_south_door_swing(self, tool: SpatialCalculatorTool) -> None:
        """Test door swing calculation for south wall door."""
        room = Room(
            width=5.0,
            depth=4.0,
            room_type=RoomType.BEDROOM,
            doors=[DoorPosition(wall=WallSide.SOUTH, offset=2.5, width=0.9)],
        )
        input_data = SpatialAnalysisInput(room=room)
        result = await tool.execute(input_data)

        assert result.success is True
        door_swing = result.data.get_zones_by_type(ZoneType.DOOR_SWING)[0]
        assert door_swing.z_max == 4.0  # Against south wall

    @pytest.mark.asyncio
    async def test_east_door_swing(self, tool: SpatialCalculatorTool) -> None:
        """Test door swing calculation for east wall door."""
        room = Room(
            width=5.0,
            depth=4.0,
            room_type=RoomType.BEDROOM,
            doors=[DoorPosition(wall=WallSide.EAST, offset=2.0, width=0.9)],
        )
        input_data = SpatialAnalysisInput(room=room)
        result = await tool.execute(input_data)

        assert result.success is True
        door_swing = result.data.get_zones_by_type(ZoneType.DOOR_SWING)[0]
        assert door_swing.x_max == 5.0  # Against east wall

    @pytest.mark.asyncio
    async def test_west_door_swing(self, tool: SpatialCalculatorTool) -> None:
        """Test door swing calculation for west wall door."""
        room = Room(
            width=5.0,
            depth=4.0,
            room_type=RoomType.BEDROOM,
            doors=[DoorPosition(wall=WallSide.WEST, offset=2.0, width=0.9)],
        )
        input_data = SpatialAnalysisInput(room=room)
        result = await tool.execute(input_data)

        assert result.success is True
        door_swing = result.data.get_zones_by_type(ZoneType.DOOR_SWING)[0]
        assert door_swing.x_min == 0  # Against west wall
