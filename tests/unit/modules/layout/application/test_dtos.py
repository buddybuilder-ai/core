"""Tests for Application Layer DTOs."""

import pytest

from src.modules.layout.application.dtos import (
    AgentContext,
    AgentPhase,
    AgentState,
    AnalysisZone,
    BatchPlacementResult,
    CommandPosition,
    FengShuiDirection,
    LayoutOutput,
    PlacedFurniture,
    PlacementAttempt,
    PlacementFailureReason,
    PlacementResult,
    PlacementStatus,
    PlacementStrategy,
    SpatialAnalysisResult,
    TrafficFlowAnalysis,
    UserPreferences,
    ZoneQuality,
)
from src.modules.layout.domain.entities import Room, RoomType
from src.modules.layout.domain.value_objects import FengShuiScore


class TestAgentPhase:
    """Tests for AgentPhase enum."""

    def test_all_phases_exist(self) -> None:
        """Test all phases exist."""
        assert AgentPhase.INITIALIZATION == "initialization"
        assert AgentPhase.INPUT_ANALYSIS == "input_analysis"
        assert AgentPhase.COMPLETED == "completed"
        assert AgentPhase.FAILED == "failed"


class TestPlacementStrategy:
    """Tests for PlacementStrategy enum."""

    def test_strategies_exist(self) -> None:
        """Test all strategies exist."""
        assert PlacementStrategy.COMMAND_POSITION == "command_position"
        assert PlacementStrategy.WALL_ALIGNED == "wall_aligned"
        assert PlacementStrategy.GRID_BASED == "grid_based"


class TestUserPreferences:
    """Tests for UserPreferences dataclass."""

    def test_default_values(self) -> None:
        """Test default preference values."""
        prefs = UserPreferences()
        assert prefs.budget_level == "medium"
        assert prefs.style_preference == "modern"
        assert prefs.accessibility_needs == []

    def test_custom_values(self) -> None:
        """Test custom preference values."""
        prefs = UserPreferences(
            budget_level="high",
            accessibility_needs=["wheelchair_accessible"],
        )
        assert prefs.budget_level == "high"
        assert "wheelchair_accessible" in prefs.accessibility_needs


class TestPlacedFurniture:
    """Tests for PlacedFurniture dataclass."""

    @pytest.fixture
    def furniture(self) -> PlacedFurniture:
        """Create test furniture."""
        return PlacedFurniture(
            id="bed_1",
            furniture_id="queen_bed",
            name="Queen Bed",
            category="bed",
            pos_x=1.0,
            pos_z=0.5,
            width=2.0,
            depth=1.8,
            height=0.5,
            rotation=0,
            is_essential=True,
        )

    def test_create_furniture(self, furniture: PlacedFurniture) -> None:
        """Test creating placed furniture."""
        assert furniture.id == "bed_1"
        assert furniture.pos_x == 1.0
        assert furniture.is_essential

    def test_end_coordinates(self, furniture: PlacedFurniture) -> None:
        """Test end coordinate calculations."""
        assert furniture.end_x == pytest.approx(3.0)  # 1.0 + 2.0
        assert furniture.end_z == pytest.approx(2.3)  # 0.5 + 1.8

    def test_center_coordinates(self, furniture: PlacedFurniture) -> None:
        """Test center coordinate calculations."""
        assert furniture.center_x == pytest.approx(2.0)
        assert furniture.center_z == pytest.approx(1.4)

    def test_rotated_dimensions(self) -> None:
        """Test dimensions when rotated 90 degrees."""
        furniture = PlacedFurniture(
            id="test",
            furniture_id="test",
            name="Test",
            category="test",
            pos_x=0,
            pos_z=0,
            width=2.0,
            depth=1.0,
            height=0.5,
            rotation=90,
        )
        # When rotated 90 degrees, width and depth are swapped
        assert furniture.end_x == pytest.approx(1.0)  # depth becomes width
        assert furniture.end_z == pytest.approx(2.0)  # width becomes depth

    def test_to_dict(self, furniture: PlacedFurniture) -> None:
        """Test conversion to dictionary."""
        result = furniture.to_dict()
        assert result["id"] == "bed_1"
        assert result["position"]["x"] == 1.0
        assert result["dimensions"]["width"] == 2.0
        assert result["is_essential"] is True


class TestAgentContext:
    """Tests for AgentContext dataclass."""

    @pytest.fixture
    def room(self) -> Room:
        """Create test room."""
        return Room(
            width=5.0,
            depth=4.0,
            room_type=RoomType.BEDROOM,
        )

    @pytest.fixture
    def context(self, room: Room) -> AgentContext:
        """Create test context."""
        return AgentContext(
            room=room,
            room_type="bedroom",
        )

    def test_create_context(self, context: AgentContext) -> None:
        """Test creating agent context."""
        assert context.room_type == "bedroom"
        assert context.phase == AgentPhase.INITIALIZATION
        assert context.retry_count == 0

    def test_is_completed(self, context: AgentContext) -> None:
        """Test is_completed property."""
        assert not context.is_completed
        context.phase = AgentPhase.COMPLETED
        assert context.is_completed

    def test_is_failed(self, context: AgentContext) -> None:
        """Test is_failed property."""
        assert not context.is_failed
        context.phase = AgentPhase.FAILED
        assert context.is_failed

    def test_can_retry(self, context: AgentContext) -> None:
        """Test can_retry property."""
        assert context.can_retry
        context.retry_count = 3
        assert not context.can_retry

    def test_advance_phase(self, context: AgentContext) -> None:
        """Test advancing phase."""
        context.advance_phase(AgentPhase.SPATIAL_ANALYSIS)
        assert context.phase == AgentPhase.SPATIAL_ANALYSIS

    def test_add_error(self, context: AgentContext) -> None:
        """Test adding validation error."""
        context.add_error("Test error")
        assert len(context.validation_errors) == 1
        assert "Test error" in context.validation_errors

    def test_increment_retry(self, context: AgentContext) -> None:
        """Test incrementing retry count."""
        assert context.can_retry
        result1 = context.increment_retry()
        assert context.retry_count == 1
        assert result1  # First retry still under limit

        result2 = context.increment_retry()
        assert context.retry_count == 2
        assert result2  # Second retry still under limit

        result3 = context.increment_retry()
        assert context.retry_count == 3
        assert not result3  # Third retry hits the limit (3 == max_retries)
        assert not context.can_retry  # Can no longer retry

    def test_essential_furniture_placed(self, context: AgentContext) -> None:
        """Test essential furniture check."""
        context.selected_furniture = [
            {"category": "bed", "is_essential": True},
        ]
        assert not context.essential_furniture_placed

        context.placed_furniture.append(
            PlacedFurniture(
                id="bed_1",
                furniture_id="bed",
                name="Bed",
                category="bed",
                pos_x=0,
                pos_z=0,
                width=2,
                depth=1.8,
                height=0.5,
                is_essential=True,
            )
        )
        assert context.essential_furniture_placed


class TestAgentState:
    """Tests for AgentState dataclass."""

    def test_from_context(self) -> None:
        """Test creating state from context."""
        room = Room(width=5.0, depth=4.0, room_type=RoomType.BEDROOM)
        context = AgentContext(
            room=room,
            room_type="bedroom",
            phase=AgentPhase.PLACEMENT_EXECUTION,
            feng_shui_score=FengShuiScore(
                command_position=25,
                five_elements=15,
                chi_flow=20,
                sha_chi_avoidance=15,
            ),
        )
        context.placed_furniture.append(
            PlacedFurniture(
                id="test",
                furniture_id="test",
                name="Test",
                category="test",
                pos_x=0,
                pos_z=0,
                width=1,
                depth=1,
                height=1,
            )
        )
        context.add_error("Error 1")
        context.add_warning("Warning 1")

        state = AgentState.from_context(context)

        assert state.phase == AgentPhase.PLACEMENT_EXECUTION
        assert state.placed_count == 1
        assert state.score == 75
        assert state.errors == 1
        assert state.warnings == 1


class TestZoneQuality:
    """Tests for ZoneQuality enum."""

    def test_qualities_exist(self) -> None:
        """Test all qualities exist."""
        assert ZoneQuality.EXCELLENT == "excellent"
        assert ZoneQuality.GOOD == "good"
        assert ZoneQuality.AVOID == "avoid"


class TestFengShuiDirection:
    """Tests for FengShuiDirection enum."""

    def test_directions_exist(self) -> None:
        """Test all directions exist."""
        assert FengShuiDirection.NORTH == "north"
        assert FengShuiDirection.SOUTH == "south"
        assert FengShuiDirection.CENTER == "center"


class TestAnalysisZone:
    """Tests for AnalysisZone dataclass."""

    @pytest.fixture
    def zone(self) -> AnalysisZone:
        """Create test zone."""
        return AnalysisZone(
            zone_type="command",
            x=1.0,
            z=0.5,
            width=2.0,
            depth=1.5,
            quality=ZoneQuality.EXCELLENT,
        )

    def test_create_zone(self, zone: AnalysisZone) -> None:
        """Test creating analysis zone."""
        assert zone.zone_type == "command"
        assert zone.quality == ZoneQuality.EXCELLENT

    def test_area(self, zone: AnalysisZone) -> None:
        """Test area calculation."""
        assert zone.area == pytest.approx(3.0)

    def test_center_coordinates(self, zone: AnalysisZone) -> None:
        """Test center coordinates."""
        assert zone.center_x == pytest.approx(2.0)
        assert zone.center_z == pytest.approx(1.25)

    def test_contains_point(self, zone: AnalysisZone) -> None:
        """Test point containment."""
        assert zone.contains_point(2.0, 1.0)
        assert not zone.contains_point(0, 0)

    def test_to_dict(self, zone: AnalysisZone) -> None:
        """Test conversion to dictionary."""
        result = zone.to_dict()
        assert result["zone_type"] == "command"
        assert result["quality"] == "excellent"


class TestCommandPosition:
    """Tests for CommandPosition dataclass."""

    def test_create_command_position(self) -> None:
        """Test creating command position."""
        pos = CommandPosition(
            x=3.0,
            z=2.0,
            facing_direction=FengShuiDirection.SOUTH,
            quality=ZoneQuality.EXCELLENT,
            has_solid_backing=True,
            can_see_door=True,
            score=85.0,
        )
        assert pos.x == 3.0
        assert pos.score == 85.0

    def test_to_dict(self) -> None:
        """Test conversion to dictionary."""
        pos = CommandPosition(
            x=3.0,
            z=2.0,
            facing_direction=FengShuiDirection.SOUTH,
            quality=ZoneQuality.GOOD,
            score=75.0,
        )
        result = pos.to_dict()
        assert result["position"]["x"] == 3.0
        assert result["facing_direction"] == "south"


class TestTrafficFlowAnalysis:
    """Tests for TrafficFlowAnalysis dataclass."""

    def test_create_traffic_flow(self) -> None:
        """Test creating traffic flow analysis."""
        flow = TrafficFlowAnalysis(
            main_path_width=0.8,
            has_clear_path=True,
            chi_flow_quality=ZoneQuality.GOOD,
        )
        assert flow.main_path_width == 0.8
        assert flow.has_clear_path

    def test_to_dict(self) -> None:
        """Test conversion to dictionary."""
        flow = TrafficFlowAnalysis(
            main_path_width=0.6,
            has_clear_path=False,
        )
        result = flow.to_dict()
        assert result["main_path_width"] == 0.6
        assert result["has_clear_path"] is False


class TestSpatialAnalysisResult:
    """Tests for SpatialAnalysisResult dataclass."""

    @pytest.fixture
    def result(self) -> SpatialAnalysisResult:
        """Create test result."""
        return SpatialAnalysisResult(
            room_area=20.0,
            usable_area=15.0,
            command_positions=[
                CommandPosition(
                    x=3.0,
                    z=2.0,
                    facing_direction=FengShuiDirection.SOUTH,
                    quality=ZoneQuality.EXCELLENT,
                    score=90.0,
                ),
                CommandPosition(
                    x=1.0,
                    z=2.0,
                    facing_direction=FengShuiDirection.EAST,
                    quality=ZoneQuality.GOOD,
                    score=70.0,
                ),
            ],
        )

    def test_usable_ratio(self, result: SpatialAnalysisResult) -> None:
        """Test usable ratio calculation."""
        assert result.usable_ratio == pytest.approx(0.75)

    def test_best_command_position(self, result: SpatialAnalysisResult) -> None:
        """Test getting best command position."""
        best = result.best_command_position
        assert best is not None
        assert best.score == 90.0


class TestPlacementStatus:
    """Tests for PlacementStatus enum."""

    def test_statuses_exist(self) -> None:
        """Test all statuses exist."""
        assert PlacementStatus.SUCCESS == "success"
        assert PlacementStatus.PARTIAL == "partial"
        assert PlacementStatus.FAILED == "failed"


class TestPlacementFailureReason:
    """Tests for PlacementFailureReason enum."""

    def test_reasons_exist(self) -> None:
        """Test all reasons exist."""
        assert PlacementFailureReason.NO_SPACE == "no_space"
        assert PlacementFailureReason.COLLISION == "collision"
        assert PlacementFailureReason.FENG_SHUI_VIOLATION == "feng_shui_violation"


class TestPlacementAttempt:
    """Tests for PlacementAttempt dataclass."""

    def test_create_attempt(self) -> None:
        """Test creating placement attempt."""
        attempt = PlacementAttempt(
            furniture_id="bed_1",
            furniture_name="Queen Bed",
            pos_x=1.0,
            pos_z=0.5,
            rotation=0,
            strategy=PlacementStrategy.COMMAND_POSITION,
            success=True,
        )
        assert attempt.success
        assert attempt.failure_reason is None

    def test_failed_attempt(self) -> None:
        """Test creating failed attempt."""
        attempt = PlacementAttempt(
            furniture_id="desk_1",
            furniture_name="Desk",
            pos_x=0,
            pos_z=0,
            rotation=0,
            strategy=PlacementStrategy.WALL_ALIGNED,
            success=False,
            failure_reason=PlacementFailureReason.COLLISION,
        )
        assert not attempt.success
        assert attempt.failure_reason == PlacementFailureReason.COLLISION


class TestPlacementResult:
    """Tests for PlacementResult dataclass."""

    def test_successful_result(self) -> None:
        """Test successful placement result."""
        furniture = PlacedFurniture(
            id="test",
            furniture_id="test",
            name="Test",
            category="test",
            pos_x=1,
            pos_z=1,
            width=1,
            depth=1,
            height=1,
        )
        result = PlacementResult(
            furniture=furniture,
            status=PlacementStatus.SUCCESS,
        )
        assert result.is_success

    def test_failed_result(self) -> None:
        """Test failed placement result."""
        result = PlacementResult(
            furniture=None,
            status=PlacementStatus.FAILED,
        )
        assert not result.is_success


class TestBatchPlacementResult:
    """Tests for BatchPlacementResult dataclass."""

    def test_success_rate(self) -> None:
        """Test success rate calculation."""
        batch = BatchPlacementResult(
            total_items=10,
            placed_count=7,
            failed_count=3,
        )
        assert batch.success_rate == pytest.approx(0.7)

    def test_get_placed_furniture(self) -> None:
        """Test getting placed furniture."""
        furniture = PlacedFurniture(
            id="test",
            furniture_id="test",
            name="Test",
            category="test",
            pos_x=0,
            pos_z=0,
            width=1,
            depth=1,
            height=1,
        )
        batch = BatchPlacementResult(
            results=[
                PlacementResult(
                    furniture=furniture,
                    status=PlacementStatus.SUCCESS,
                ),
                PlacementResult(
                    furniture=None,
                    status=PlacementStatus.FAILED,
                ),
            ]
        )
        placed = batch.get_placed_furniture()
        assert len(placed) == 1


class TestLayoutOutput:
    """Tests for LayoutOutput dataclass."""

    def test_to_dict(self) -> None:
        """Test conversion to dictionary."""
        furniture = PlacedFurniture(
            id="bed_1",
            furniture_id="queen_bed",
            name="Queen Bed",
            category="bed",
            pos_x=1.0,
            pos_z=0.5,
            width=2.0,
            depth=1.8,
            height=0.5,
        )
        output = LayoutOutput(
            room_type="bedroom",
            room_dimensions={"width": 5.0, "depth": 4.0},
            furniture=[furniture],
            feng_shui_score=85.0,
        )
        result = output.to_dict()
        assert result["room_type"] == "bedroom"
        assert result["feng_shui_score"] == 85.0
        assert len(result["furniture"]) == 1

    def test_to_json_layout(self) -> None:
        """Test conversion to simplified JSON layout."""
        furniture = PlacedFurniture(
            id="bed_1",
            furniture_id="queen_bed",
            name="Queen Bed",
            category="bed",
            pos_x=1.0,
            pos_z=0.5,
            width=2.0,
            depth=1.8,
            height=0.5,
        )
        output = LayoutOutput(
            room_type="bedroom",
            room_dimensions={"width": 5.0, "depth": 4.0},
            furniture=[furniture],
            feng_shui_score=85.0,
        )
        result = output.to_json_layout()
        assert result["room"]["type"] == "bedroom"
        assert result["room"]["width"] == 5.0
        assert len(result["items"]) == 1
        assert result["items"][0]["x"] == 1.0
