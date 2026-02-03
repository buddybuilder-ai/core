"""Tests for agent request/response Pydantic schemas."""

import pytest
from pydantic import ValidationError

from src.schemas.layout import RoomDimensions
from src.schemas.layout.agent import (
    AgentContext,
    AgentExecutionTrace,
    AgentStep,
    FengShuiLayoutRequest,
    FengShuiLayoutResponse,
    LayoutConstraint,
    LayoutMetadata,
    PlacedFurnitureItem,
    ToolCallResult,
)
from src.schemas.layout.feng_shui import (
    DoorPosition,
    FengShuiScoreBreakdown,
    FurnitureDimensions,
    RoomType,
    WallSide,
    WindowPosition,
)


class TestFengShuiLayoutRequest:
    """Tests for FengShuiLayoutRequest schema."""

    def test_valid_request(self) -> None:
        """Test creating valid request."""
        request = FengShuiLayoutRequest(
            dimensions=RoomDimensions(width=5.0, depth=4.0),
            room_type=RoomType.BEDROOM,
            doors=[DoorPosition(wall=WallSide.SOUTH, offset=2.0)],
            windows=[WindowPosition(wall=WallSide.EAST, offset=1.5, width=1.5)],
        )
        assert request.dimensions.width == 5.0
        assert request.room_type == RoomType.BEDROOM
        assert len(request.doors) == 1
        assert len(request.windows) == 1

    def test_request_with_defaults(self) -> None:
        """Test request with default values."""
        request = FengShuiLayoutRequest(
            dimensions=RoomDimensions(width=4.0, depth=3.0),
            room_type=RoomType.OFFICE,
        )
        assert request.doors == []
        assert request.windows == []
        assert request.budget_level == "medium"
        assert request.direction == "north"

    def test_invalid_budget_level(self) -> None:
        """Test that invalid budget level raises error."""
        with pytest.raises(ValidationError) as exc_info:
            FengShuiLayoutRequest(
                dimensions=RoomDimensions(width=4.0, depth=3.0),
                room_type=RoomType.BEDROOM,
                budget_level="expensive",  # invalid
            )
        assert "budget_level" in str(exc_info.value)

    def test_request_with_preferences(self) -> None:
        """Test request with user preferences."""
        request = FengShuiLayoutRequest(
            dimensions=RoomDimensions(width=5.0, depth=4.0),
            room_type=RoomType.LIVING_ROOM,
            user_preferences={
                "preferred_colors": ["blue", "white"],
                "avoid_furniture": ["recliner"],
            },
        )
        assert request.user_preferences is not None
        assert "preferred_colors" in request.user_preferences


class TestPlacedFurnitureItem:
    """Tests for PlacedFurnitureItem schema."""

    def test_valid_placed_item(self) -> None:
        """Test creating valid placed furniture item."""
        item = PlacedFurnitureItem(
            id="bed_001",
            name="Queen Bed",
            category="bed",
            pos_x=2.5,
            pos_z=3.0,
            rotation=90,
            dimensions=FurnitureDimensions(width=1.6, depth=2.0, height=0.5),
        )
        assert item.id == "bed_001"
        assert item.pos_x == 2.5
        assert item.pos_y == 0.0  # default
        assert item.rotation == 90

    def test_placed_item_with_feng_shui_notes(self) -> None:
        """Test placed item with feng shui notes."""
        item = PlacedFurnitureItem(
            id="desk_001",
            name="Office Desk",
            category="desk",
            pos_x=1.5,
            pos_z=2.0,
            dimensions=FurnitureDimensions(width=1.4, depth=0.7, height=0.75),
            feng_shui_notes=[
                "Placed in command position",
                "Has view of door",
            ],
        )
        assert len(item.feng_shui_notes) == 2

    def test_invalid_rotation(self) -> None:
        """Test that invalid rotation raises error."""
        with pytest.raises(ValidationError):
            PlacedFurnitureItem(
                id="sofa_001",
                name="Sofa",
                category="sofa",
                pos_x=2.0,
                pos_z=1.5,
                rotation=400,  # >= 360
                dimensions=FurnitureDimensions(width=2.0, depth=0.9, height=0.85),
            )


class TestLayoutConstraint:
    """Tests for LayoutConstraint schema."""

    def test_valid_constraint(self) -> None:
        """Test creating valid constraint."""
        constraint = LayoutConstraint(
            constraint_type="clearance",
            description="Minimum 60cm walkway between furniture",
            satisfied=True,
        )
        assert constraint.constraint_type == "clearance"
        assert constraint.satisfied is True
        assert constraint.severity == "warning"

    def test_constraint_severity(self) -> None:
        """Test constraint with custom severity."""
        constraint = LayoutConstraint(
            constraint_type="safety",
            description="Emergency exit must not be blocked",
            satisfied=False,
            severity="error",
        )
        assert constraint.severity == "error"


class TestLayoutMetadata:
    """Tests for LayoutMetadata schema."""

    def test_default_metadata(self) -> None:
        """Test metadata with default values."""
        metadata = LayoutMetadata()
        assert metadata.layout_id is not None
        assert metadata.generated_at is not None
        assert metadata.version == "1.0"
        assert metadata.generation_time_ms == 0

    def test_metadata_with_values(self) -> None:
        """Test metadata with custom values."""
        metadata = LayoutMetadata(
            generation_time_ms=1500,
            retries=2,
            agent_model="gpt-4-turbo",
        )
        assert metadata.generation_time_ms == 1500
        assert metadata.retries == 2


class TestFengShuiLayoutResponse:
    """Tests for FengShuiLayoutResponse schema."""

    @pytest.fixture
    def sample_response(self) -> FengShuiLayoutResponse:
        """Create sample response for testing."""
        return FengShuiLayoutResponse(
            items=[
                PlacedFurnitureItem(
                    id="bed_001",
                    name="Queen Bed",
                    category="bed",
                    pos_x=2.5,
                    pos_z=3.0,
                    dimensions=FurnitureDimensions(width=1.6, depth=2.0, height=0.5),
                    is_essential=True,
                ),
                PlacedFurnitureItem(
                    id="nightstand_001",
                    name="Nightstand",
                    category="nightstand",
                    pos_x=1.0,
                    pos_z=3.0,
                    dimensions=FurnitureDimensions(width=0.5, depth=0.4, height=0.6),
                    is_essential=False,
                ),
            ],
            feng_shui_score=FengShuiScoreBreakdown(
                command_position=25,
                five_elements_balance=15,
                chi_flow=20,
                sha_chi_avoidance=18,
            ),
            reasoning="Bed placed in command position with solid wall backing.",
        )

    def test_valid_response(self, sample_response: FengShuiLayoutResponse) -> None:
        """Test creating valid response."""
        assert len(sample_response.items) == 2
        assert sample_response.feng_shui_score.total == 78

    def test_success_property(self, sample_response: FengShuiLayoutResponse) -> None:
        """Test success property."""
        assert sample_response.success is True

    def test_furniture_count_property(
        self, sample_response: FengShuiLayoutResponse
    ) -> None:
        """Test furniture_count property."""
        assert sample_response.furniture_count == 2

    def test_essential_count_property(
        self, sample_response: FengShuiLayoutResponse
    ) -> None:
        """Test essential_count property."""
        assert sample_response.essential_count == 1

    def test_response_with_constraints(self) -> None:
        """Test response with constraints."""
        response = FengShuiLayoutResponse(
            items=[],
            feng_shui_score=FengShuiScoreBreakdown(
                command_position=10,
                five_elements_balance=5,
                chi_flow=10,
                sha_chi_avoidance=10,
            ),
            constraints=[
                LayoutConstraint(
                    constraint_type="safety",
                    description="Emergency exit blocked",
                    satisfied=False,
                    severity="error",
                ),
            ],
            reasoning="Could not place furniture safely.",
        )
        # Success should be False due to error constraint
        assert response.success is False

    def test_response_with_warnings_and_skipped(self) -> None:
        """Test response with warnings and skipped items."""
        response = FengShuiLayoutResponse(
            items=[
                PlacedFurnitureItem(
                    id="bed_001",
                    name="Bed",
                    category="bed",
                    pos_x=2.0,
                    pos_z=2.0,
                    dimensions=FurnitureDimensions(width=1.6, depth=2.0, height=0.5),
                ),
            ],
            feng_shui_score=FengShuiScoreBreakdown(
                command_position=20,
                five_elements_balance=10,
                chi_flow=15,
                sha_chi_avoidance=15,
            ),
            reasoning="Layout generated with some limitations.",
            warnings=["Room is smaller than recommended for bedroom"],
            skipped_items=["wardrobe_001", "dresser_001"],
        )
        assert len(response.warnings) == 1
        assert len(response.skipped_items) == 2


class TestAgentContext:
    """Tests for AgentContext schema."""

    def test_default_context(self) -> None:
        """Test context with default values."""
        context = AgentContext()
        assert context.session_id is not None
        assert context.max_retries == 3
        assert context.strict_mode is False
        assert context.debug is False

    def test_record_attempt(self) -> None:
        """Test recording attempt scores."""
        context = AgentContext()
        context.record_attempt(65)
        context.record_attempt(72)
        assert context.attempt_count == 2
        assert context.best_score == 72

    def test_should_retry(self) -> None:
        """Test should_retry logic."""
        context = AgentContext(max_retries=3)

        # Should retry when no attempts yet
        assert context.should_retry is True

        # Should retry when score below 40
        context.record_attempt(35)
        assert context.should_retry is True

        # Should not retry when score >= 40
        context.record_attempt(50)
        assert context.should_retry is False

    def test_max_retries_reached(self) -> None:
        """Test retry stops at max_retries."""
        context = AgentContext(max_retries=2)
        context.record_attempt(30)
        context.record_attempt(35)
        # Max retries reached, should not retry
        assert context.should_retry is False


class TestToolCallResult:
    """Tests for ToolCallResult schema."""

    def test_successful_call(self) -> None:
        """Test successful tool call result."""
        result = ToolCallResult(
            tool_name="COLLISION_DETECTOR",
            success=True,
            result={"collisions": [], "has_collisions": False},
            execution_time_ms=50,
        )
        assert result.success is True
        assert result.error is None

    def test_failed_call(self) -> None:
        """Test failed tool call result."""
        result = ToolCallResult(
            tool_name="RAG_SEARCH",
            success=False,
            error="Connection timeout",
            execution_time_ms=5000,
        )
        assert result.success is False
        assert result.error == "Connection timeout"


class TestAgentStep:
    """Tests for AgentStep schema."""

    def test_valid_step(self) -> None:
        """Test creating valid agent step."""
        step = AgentStep(
            step_number=1,
            step_name="Spatial Analysis",
            description="Analyzing room dimensions and constraints",
            tool_calls=[
                ToolCallResult(
                    tool_name="SPATIAL_CALCULATOR",
                    success=True,
                    execution_time_ms=100,
                ),
            ],
            reasoning="Room has sufficient space for bedroom furniture",
            duration_ms=150,
        )
        assert step.step_number == 1
        assert len(step.tool_calls) == 1


class TestAgentExecutionTrace:
    """Tests for AgentExecutionTrace schema."""

    def test_valid_trace(self) -> None:
        """Test creating valid execution trace."""
        trace = AgentExecutionTrace(
            session_id="test-session-123",
            request=FengShuiLayoutRequest(
                dimensions=RoomDimensions(width=5.0, depth=4.0),
                room_type=RoomType.BEDROOM,
            ),
            steps=[
                AgentStep(
                    step_number=1,
                    step_name="Input Analysis",
                    description="Validating input",
                    duration_ms=50,
                ),
                AgentStep(
                    step_number=2,
                    step_name="Placement",
                    description="Placing furniture",
                    duration_ms=500,
                ),
            ],
            total_duration_ms=550,
            final_score=75,
            success=True,
        )
        assert trace.session_id == "test-session-123"
        assert len(trace.steps) == 2
        assert trace.success is True


class TestSchemaIntegration:
    """Integration tests for schema combinations."""

    def test_full_workflow_schemas(self) -> None:
        """Test creating all schemas in a typical workflow."""
        # 1. Create request
        request = FengShuiLayoutRequest(
            dimensions=RoomDimensions(width=5.0, depth=4.0),
            room_type=RoomType.BEDROOM,
            doors=[DoorPosition(wall=WallSide.SOUTH, offset=2.0)],
            windows=[WindowPosition(wall=WallSide.EAST, offset=1.5, width=1.5)],
        )

        # 2. Create context
        context = AgentContext(user_id="user_123", strict_mode=True)

        # 3. Create response
        response = FengShuiLayoutResponse(
            items=[
                PlacedFurnitureItem(
                    id="bed_001",
                    name="Bed",
                    category="bed",
                    pos_x=2.5,
                    pos_z=3.0,
                    dimensions=FurnitureDimensions(width=1.6, depth=2.0, height=0.5),
                ),
            ],
            feng_shui_score=FengShuiScoreBreakdown(
                command_position=25,
                five_elements_balance=15,
                chi_flow=20,
                sha_chi_avoidance=18,
            ),
            reasoning="Generated optimal layout.",
        )

        # 4. Record attempt
        context.record_attempt(response.feng_shui_score.total)

        assert request.room_type == RoomType.BEDROOM
        assert response.success is True
        assert context.best_score == 78

    def test_json_round_trip(self) -> None:
        """Test JSON serialization round trip."""
        request = FengShuiLayoutRequest(
            dimensions=RoomDimensions(width=5.0, depth=4.0),
            room_type=RoomType.BEDROOM,
        )

        # Serialize to JSON
        json_str = request.model_dump_json()

        # Deserialize back
        request_back = FengShuiLayoutRequest.model_validate_json(json_str)

        assert request_back.dimensions.width == 5.0
        assert request_back.room_type == RoomType.BEDROOM
