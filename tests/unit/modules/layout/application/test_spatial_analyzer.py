"""Tests for Spatial Analyzer Service."""

import pytest

from src.modules.layout.application.dtos import (
    AgentContext,
    ZoneQuality,
)
from src.modules.layout.application.services import SpatialAnalyzer
from src.modules.layout.domain.entities import (
    DoorPosition,
    Room,
    RoomType,
    WallSide,
    WindowPosition,
)


class TestSpatialAnalyzer:
    """Tests for SpatialAnalyzer service."""

    @pytest.fixture
    def analyzer(self) -> SpatialAnalyzer:
        """Create spatial analyzer instance."""
        return SpatialAnalyzer()

    @pytest.fixture
    def bedroom(self) -> Room:
        """Create standard bedroom for testing."""
        return Room(
            width=5.0,
            depth=4.0,
            height=2.8,
            room_type=RoomType.BEDROOM,
            doors=[
                DoorPosition(wall=WallSide.SOUTH, offset=2.0, width=0.9),
            ],
            windows=[
                WindowPosition(wall=WallSide.EAST, offset=1.5, width=1.5, height=1.2),
            ],
        )

    @pytest.fixture
    def office(self) -> Room:
        """Create office for testing."""
        return Room(
            width=4.0,
            depth=3.5,
            height=2.8,
            room_type=RoomType.OFFICE,
            doors=[
                DoorPosition(wall=WallSide.SOUTH, offset=1.5, width=0.9),
            ],
            windows=[
                WindowPosition(wall=WallSide.NORTH, offset=1.0, width=2.0, height=1.2),
            ],
        )

    @pytest.fixture
    def room_with_two_doors(self) -> Room:
        """Create room with two doors for testing."""
        return Room(
            width=6.0,
            depth=5.0,
            height=2.8,
            room_type=RoomType.LIVING_ROOM,
            doors=[
                DoorPosition(wall=WallSide.SOUTH, offset=2.0, width=0.9),
                DoorPosition(wall=WallSide.EAST, offset=2.0, width=0.9),
            ],
            windows=[
                WindowPosition(wall=WallSide.NORTH, offset=1.5, width=2.0, height=1.5),
            ],
        )


class TestAnalyze:
    """Tests for analyze method."""

    @pytest.fixture
    def analyzer(self) -> SpatialAnalyzer:
        """Create spatial analyzer instance."""
        return SpatialAnalyzer()

    @pytest.fixture
    def bedroom(self) -> Room:
        """Create standard bedroom for testing."""
        return Room(
            width=5.0,
            depth=4.0,
            height=2.8,
            room_type=RoomType.BEDROOM,
            doors=[
                DoorPosition(wall=WallSide.SOUTH, offset=2.0, width=0.9),
            ],
            windows=[
                WindowPosition(wall=WallSide.EAST, offset=1.5, width=1.5, height=1.2),
            ],
        )

    def test_analyze_returns_result(
        self, analyzer: SpatialAnalyzer, bedroom: Room
    ) -> None:
        """Test that analyze returns a result."""
        result = analyzer.analyze(bedroom)
        assert result is not None
        assert result.room_area > 0
        assert result.usable_area > 0

    def test_analyze_calculates_room_area(
        self, analyzer: SpatialAnalyzer, bedroom: Room
    ) -> None:
        """Test room area calculation."""
        result = analyzer.analyze(bedroom)
        assert result.room_area == pytest.approx(20.0)  # 5 * 4

    def test_analyze_calculates_usable_area(
        self, analyzer: SpatialAnalyzer, bedroom: Room
    ) -> None:
        """Test usable area calculation."""
        result = analyzer.analyze(bedroom)
        # Usable area should be less than room area (door swing subtracted)
        assert result.usable_area < result.room_area
        assert result.usable_area > result.room_area * 0.5

    def test_analyze_usable_ratio(
        self, analyzer: SpatialAnalyzer, bedroom: Room
    ) -> None:
        """Test usable ratio property."""
        result = analyzer.analyze(bedroom)
        assert 0.5 < result.usable_ratio < 1.0

    def test_analyze_finds_command_positions(
        self, analyzer: SpatialAnalyzer, bedroom: Room
    ) -> None:
        """Test that command positions are found."""
        result = analyzer.analyze(bedroom)
        assert len(result.command_positions) > 0
        # Best position should have highest score
        best = result.best_command_position
        assert best is not None
        assert best.score > 0

    def test_analyze_identifies_zones(
        self, analyzer: SpatialAnalyzer, bedroom: Room
    ) -> None:
        """Test that zones are identified."""
        result = analyzer.analyze(bedroom)
        assert len(result.zones) > 0
        # Should have traffic zone near door
        traffic_zones = [z for z in result.zones if z.zone_type == "traffic"]
        assert len(traffic_zones) > 0

    def test_analyze_traffic_flow(
        self, analyzer: SpatialAnalyzer, bedroom: Room
    ) -> None:
        """Test traffic flow analysis."""
        result = analyzer.analyze(bedroom)
        assert result.traffic_flow is not None
        assert result.traffic_flow.main_path_width > 0
        assert result.traffic_flow.has_clear_path


class TestCommandPositions:
    """Tests for command position finding."""

    @pytest.fixture
    def analyzer(self) -> SpatialAnalyzer:
        """Create spatial analyzer instance."""
        return SpatialAnalyzer()

    def test_command_positions_found(self, analyzer: SpatialAnalyzer) -> None:
        """Test command positions are found with meaningful scores."""
        room = Room(
            width=5.0,
            depth=4.0,
            room_type=RoomType.BEDROOM,
            doors=[DoorPosition(wall=WallSide.SOUTH, offset=2.0, width=0.9)],
        )
        result = analyzer.analyze(room)
        # Command positions should be found
        assert len(result.command_positions) > 0
        # Best position should have a reasonable score
        best = result.best_command_position
        assert best is not None
        assert best.score > 0

    def test_command_position_has_solid_backing(
        self, analyzer: SpatialAnalyzer
    ) -> None:
        """Test command position has solid backing."""
        room = Room(
            width=5.0,
            depth=4.0,
            room_type=RoomType.BEDROOM,
            doors=[DoorPosition(wall=WallSide.SOUTH, offset=2.0, width=0.9)],
        )
        result = analyzer.analyze(room)
        # All positions should have solid backing (against wall)
        for pos in result.command_positions:
            assert pos.has_solid_backing

    def test_command_positions_sorted_by_score(
        self, analyzer: SpatialAnalyzer
    ) -> None:
        """Test command positions are sorted by score."""
        room = Room(
            width=5.0,
            depth=4.0,
            room_type=RoomType.BEDROOM,
            doors=[DoorPosition(wall=WallSide.SOUTH, offset=2.0, width=0.9)],
        )
        result = analyzer.analyze(room)
        if len(result.command_positions) > 1:
            for i in range(len(result.command_positions) - 1):
                assert (
                    result.command_positions[i].score
                    >= result.command_positions[i + 1].score
                )

    def test_command_position_facing_direction(
        self, analyzer: SpatialAnalyzer
    ) -> None:
        """Test command position has correct facing direction."""
        room = Room(
            width=5.0,
            depth=4.0,
            room_type=RoomType.BEDROOM,
            doors=[DoorPosition(wall=WallSide.SOUTH, offset=2.0, width=0.9)],
        )
        result = analyzer.analyze(room)
        best = result.best_command_position
        assert best is not None
        assert best.facing_direction is not None


class TestZones:
    """Tests for zone identification."""

    @pytest.fixture
    def analyzer(self) -> SpatialAnalyzer:
        """Create spatial analyzer instance."""
        return SpatialAnalyzer()

    def test_traffic_zone_near_door(self, analyzer: SpatialAnalyzer) -> None:
        """Test traffic zone is identified near door."""
        room = Room(
            width=5.0,
            depth=4.0,
            room_type=RoomType.BEDROOM,
            doors=[DoorPosition(wall=WallSide.SOUTH, offset=2.0, width=0.9)],
        )
        result = analyzer.analyze(room)
        traffic_zones = [z for z in result.zones if z.zone_type == "traffic"]
        assert len(traffic_zones) == 1
        # Traffic zone should be near south wall (door)
        assert traffic_zones[0].z < 2.0

    def test_natural_light_zone_near_window(self, analyzer: SpatialAnalyzer) -> None:
        """Test natural light zone is identified near window."""
        room = Room(
            width=5.0,
            depth=4.0,
            room_type=RoomType.BEDROOM,
            doors=[DoorPosition(wall=WallSide.SOUTH, offset=2.0, width=0.9)],
            windows=[WindowPosition(wall=WallSide.EAST, offset=1.5, width=1.5)],
        )
        result = analyzer.analyze(room)
        light_zones = [z for z in result.zones if z.zone_type == "natural_light"]
        assert len(light_zones) == 1

    def test_work_zone_identified(self, analyzer: SpatialAnalyzer) -> None:
        """Test work zone is identified in larger room."""
        room = Room(
            width=5.0,
            depth=4.0,
            room_type=RoomType.OFFICE,
            doors=[DoorPosition(wall=WallSide.SOUTH, offset=2.0, width=0.9)],
            windows=[WindowPosition(wall=WallSide.NORTH, offset=1.0, width=2.0)],
        )
        result = analyzer.analyze(room)
        work_zones = [z for z in result.zones if z.zone_type == "work"]
        assert len(work_zones) == 1

    def test_rest_zone_identified(self, analyzer: SpatialAnalyzer) -> None:
        """Test rest zone is identified."""
        room = Room(
            width=5.0,
            depth=4.0,
            room_type=RoomType.BEDROOM,
            doors=[DoorPosition(wall=WallSide.SOUTH, offset=2.0, width=0.9)],
        )
        result = analyzer.analyze(room)
        rest_zones = [z for z in result.zones if z.zone_type == "rest"]
        assert len(rest_zones) == 1
        # Rest zone should be away from door (at least half the room depth)
        assert rest_zones[0].z >= 1.5

    def test_zone_quality_set(self, analyzer: SpatialAnalyzer) -> None:
        """Test zones have quality set."""
        room = Room(
            width=5.0,
            depth=4.0,
            room_type=RoomType.BEDROOM,
            doors=[DoorPosition(wall=WallSide.SOUTH, offset=2.0, width=0.9)],
        )
        result = analyzer.analyze(room)
        for zone in result.zones:
            assert zone.quality in [
                ZoneQuality.EXCELLENT,
                ZoneQuality.GOOD,
                ZoneQuality.ACCEPTABLE,
                ZoneQuality.POOR,
                ZoneQuality.AVOID,
            ]

    def test_traffic_zone_marked_avoid(self, analyzer: SpatialAnalyzer) -> None:
        """Test traffic zones are marked as avoid."""
        room = Room(
            width=5.0,
            depth=4.0,
            room_type=RoomType.BEDROOM,
            doors=[DoorPosition(wall=WallSide.SOUTH, offset=2.0, width=0.9)],
        )
        result = analyzer.analyze(room)
        traffic_zones = [z for z in result.zones if z.zone_type == "traffic"]
        for zone in traffic_zones:
            assert zone.quality == ZoneQuality.AVOID


class TestTrafficFlow:
    """Tests for traffic flow analysis."""

    @pytest.fixture
    def analyzer(self) -> SpatialAnalyzer:
        """Create spatial analyzer instance."""
        return SpatialAnalyzer()

    def test_single_door_path_width(self, analyzer: SpatialAnalyzer) -> None:
        """Test path width with single door."""
        room = Room(
            width=5.0,
            depth=4.0,
            room_type=RoomType.BEDROOM,
            doors=[DoorPosition(wall=WallSide.SOUTH, offset=2.0, width=0.9)],
        )
        result = analyzer.analyze(room)
        # Path width should be room depth
        assert result.traffic_flow.main_path_width == pytest.approx(4.0)

    def test_two_door_path_width(self, analyzer: SpatialAnalyzer) -> None:
        """Test path width with two doors."""
        room = Room(
            width=6.0,
            depth=5.0,
            room_type=RoomType.LIVING_ROOM,
            doors=[
                DoorPosition(wall=WallSide.SOUTH, offset=2.0, width=0.9),
                DoorPosition(wall=WallSide.EAST, offset=2.0, width=0.9),
            ],
        )
        result = analyzer.analyze(room)
        assert result.traffic_flow.main_path_width > 0

    def test_has_clear_path(self, analyzer: SpatialAnalyzer) -> None:
        """Test clear path detection."""
        room = Room(
            width=5.0,
            depth=4.0,
            room_type=RoomType.BEDROOM,
            doors=[DoorPosition(wall=WallSide.SOUTH, offset=2.0, width=0.9)],
        )
        result = analyzer.analyze(room)
        # Standard room should have clear path
        assert result.traffic_flow.has_clear_path

    def test_chi_flow_quality(self, analyzer: SpatialAnalyzer) -> None:
        """Test chi flow quality assessment."""
        room = Room(
            width=5.0,
            depth=4.0,
            room_type=RoomType.BEDROOM,
            doors=[DoorPosition(wall=WallSide.SOUTH, offset=2.0, width=0.9)],
        )
        result = analyzer.analyze(room)
        assert result.traffic_flow.chi_flow_quality is not None


class TestShaChi:
    """Tests for sha chi detection."""

    @pytest.fixture
    def analyzer(self) -> SpatialAnalyzer:
        """Create spatial analyzer instance."""
        return SpatialAnalyzer()

    def test_sha_chi_aligned_doors(self, analyzer: SpatialAnalyzer) -> None:
        """Test sha chi detection with aligned opposite doors."""
        # Doors directly aligned on opposite walls
        room = Room(
            width=5.0,
            depth=4.0,
            room_type=RoomType.LIVING_ROOM,
            doors=[
                DoorPosition(wall=WallSide.SOUTH, offset=2.0, width=0.9),
                DoorPosition(wall=WallSide.NORTH, offset=2.0, width=0.9),
            ],
        )
        result = analyzer.analyze(room)
        # Sha chi should result in poor chi flow
        assert result.traffic_flow.chi_flow_quality == ZoneQuality.POOR

    def test_no_sha_chi_perpendicular_doors(self, analyzer: SpatialAnalyzer) -> None:
        """Test no sha chi with perpendicular doors."""
        room = Room(
            width=5.0,
            depth=4.0,
            room_type=RoomType.LIVING_ROOM,
            doors=[
                DoorPosition(wall=WallSide.SOUTH, offset=2.0, width=0.9),
                DoorPosition(wall=WallSide.EAST, offset=2.0, width=0.9),
            ],
        )
        result = analyzer.analyze(room)
        # No sha chi - should not be poor
        assert result.traffic_flow.chi_flow_quality != ZoneQuality.POOR


class TestUpdateContext:
    """Tests for context update method."""

    @pytest.fixture
    def analyzer(self) -> SpatialAnalyzer:
        """Create spatial analyzer instance."""
        return SpatialAnalyzer()

    @pytest.fixture
    def context(self) -> AgentContext:
        """Create agent context."""
        room = Room(
            width=5.0,
            depth=4.0,
            room_type=RoomType.BEDROOM,
            doors=[DoorPosition(wall=WallSide.SOUTH, offset=2.0, width=0.9)],
        )
        return AgentContext(room=room, room_type="bedroom")

    def test_update_context(
        self, analyzer: SpatialAnalyzer, context: AgentContext
    ) -> None:
        """Test context is updated with analysis results."""
        result = analyzer.analyze(context.room)
        analyzer.update_context(context, result)

        assert "spatial_analysis" in context.metadata
        assert context.metadata["spatial_analysis"]["room_area"] > 0
        assert context.metadata["spatial_analysis"]["usable_area"] > 0

    def test_update_context_best_command_position(
        self, analyzer: SpatialAnalyzer, context: AgentContext
    ) -> None:
        """Test best command position is stored in context."""
        result = analyzer.analyze(context.room)
        analyzer.update_context(context, result)

        if result.best_command_position:
            assert "best_command_position" in context.metadata
            assert "x" in context.metadata["best_command_position"]
            assert "z" in context.metadata["best_command_position"]
            assert "score" in context.metadata["best_command_position"]


class TestSmallRooms:
    """Tests for small room handling."""

    @pytest.fixture
    def analyzer(self) -> SpatialAnalyzer:
        """Create spatial analyzer instance."""
        return SpatialAnalyzer()

    def test_small_room_analysis(self, analyzer: SpatialAnalyzer) -> None:
        """Test analysis of small room."""
        room = Room(
            width=2.5,
            depth=2.5,
            room_type=RoomType.BEDROOM,
            doors=[DoorPosition(wall=WallSide.SOUTH, offset=0.8, width=0.9)],
        )
        result = analyzer.analyze(room)
        assert result.room_area == pytest.approx(6.25)
        # Small rooms should still have usable area
        assert result.usable_area > 0

    def test_small_room_no_work_zone(self, analyzer: SpatialAnalyzer) -> None:
        """Test very small room doesn't have work zone."""
        room = Room(
            width=2.0,
            depth=2.0,
            room_type=RoomType.BEDROOM,
            doors=[DoorPosition(wall=WallSide.SOUTH, offset=0.5, width=0.9)],
        )
        result = analyzer.analyze(room)
        work_zones = [z for z in result.zones if z.zone_type == "work"]
        assert len(work_zones) == 0


class TestRoomWithoutDoors:
    """Tests for rooms without doors."""

    @pytest.fixture
    def analyzer(self) -> SpatialAnalyzer:
        """Create spatial analyzer instance."""
        return SpatialAnalyzer()

    def test_room_without_doors(self, analyzer: SpatialAnalyzer) -> None:
        """Test analysis handles room without doors."""
        room = Room(
            width=5.0,
            depth=4.0,
            room_type=RoomType.BEDROOM,
            doors=[],
        )
        result = analyzer.analyze(room)
        # Should still find command positions using default entry
        assert len(result.command_positions) > 0
        # Should have traffic flow analysis
        assert result.traffic_flow is not None
