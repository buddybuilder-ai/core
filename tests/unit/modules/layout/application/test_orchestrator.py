"""Tests for layout orchestrator."""

import pytest

from src.modules.layout.application.agent.orchestrator import (
    LayoutOrchestrator,
    LayoutRequest,
    LayoutResponse,
    OrchestratorConfig,
    generate_layout,
)
from src.modules.layout.application.agent.state_machine import TransitionResult
from src.modules.layout.application.dtos import AgentPhase


class TestOrchestratorConfig:
    """Tests for OrchestratorConfig."""

    def test_default_config(self) -> None:
        """Test default configuration."""
        config = OrchestratorConfig()
        assert config.use_minimal_workflow is False
        assert config.max_retries == 3
        assert config.timeout_seconds == 120.0
        assert config.min_acceptable_score == 40
        assert config.auto_retry_low_score is True

    def test_custom_config(self) -> None:
        """Test custom configuration."""
        config = OrchestratorConfig(
            use_minimal_workflow=True,
            max_retries=5,
            min_acceptable_score=60,
        )
        assert config.use_minimal_workflow is True
        assert config.max_retries == 5
        assert config.min_acceptable_score == 60


class TestLayoutRequest:
    """Tests for LayoutRequest."""

    def test_request_creation(self) -> None:
        """Test creating a layout request."""
        request = LayoutRequest(
            room_type="bedroom",
            width=5.0,
            depth=4.0,
        )
        assert request.room_type == "bedroom"
        assert request.width == 5.0
        assert request.depth == 4.0
        assert request.height == 2.8  # default

    def test_request_with_all_options(self) -> None:
        """Test request with all options."""
        request = LayoutRequest(
            room_type="office",
            width=4.0,
            depth=3.0,
            height=3.0,
            budget_level="high",
            style_preference="minimalist",
            max_furniture_items=5,
            doors=[{"wall": "south", "offset": 1.5, "width": 0.9}],
            windows=[{"wall": "east", "offset": 1.0, "width": 1.5}],
        )
        assert request.budget_level == "high"
        assert len(request.doors) == 1
        assert len(request.windows) == 1

    def test_to_input_data(self) -> None:
        """Test converting request to input data."""
        request = LayoutRequest(
            room_type="bedroom",
            width=5.0,
            depth=4.0,
            budget_level="medium",
        )
        data = request.to_input_data()

        assert data["room_type"] == "bedroom"
        assert data["dimensions"]["width"] == 5.0
        assert data["preferences"]["budget_level"] == "medium"


class TestLayoutResponse:
    """Tests for LayoutResponse."""

    def test_success_response(self) -> None:
        """Test successful response."""
        response = LayoutResponse(
            success=True,
            feng_shui_score=75,
            furniture_count=5,
        )
        assert response.success is True
        assert response.feng_shui_score == 75
        assert response.error_message is None

    def test_failure_response(self) -> None:
        """Test failed response."""
        response = LayoutResponse(
            success=False,
            error_message="Phase failed",
        )
        assert response.success is False
        assert response.error_message == "Phase failed"

    def test_to_dict(self) -> None:
        """Test converting response to dict."""
        response = LayoutResponse(
            success=True,
            feng_shui_score=80,
            furniture_count=3,
            execution_time_ms=500.0,
        )
        result = response.to_dict()

        assert result["success"] is True
        assert result["feng_shui_score"] == 80
        assert result["execution_time_ms"] == 500.0


class TestLayoutOrchestrator:
    """Tests for LayoutOrchestrator."""

    @pytest.fixture
    def orchestrator(self) -> LayoutOrchestrator:
        """Create test orchestrator."""
        return LayoutOrchestrator()

    @pytest.fixture
    def bedroom_request(self) -> LayoutRequest:
        """Create bedroom layout request."""
        return LayoutRequest(
            room_type="bedroom",
            width=5.0,
            depth=4.0,
            height=2.8,
            budget_level="medium",
            max_furniture_items=5,
        )

    @pytest.fixture
    def office_request(self) -> LayoutRequest:
        """Create office layout request."""
        return LayoutRequest(
            room_type="office",
            width=4.0,
            depth=3.0,
            budget_level="low",
            max_furniture_items=3,
        )

    @pytest.mark.asyncio
    async def test_generate_bedroom_layout(
        self,
        orchestrator: LayoutOrchestrator,
        bedroom_request: LayoutRequest,
    ) -> None:
        """Test generating a bedroom layout."""
        response = await orchestrator.generate_layout(bedroom_request)

        assert response.success is True
        assert response.output is not None
        assert response.furniture_count > 0
        assert response.feng_shui_score > 0
        assert response.execution_time_ms > 0

    @pytest.mark.asyncio
    async def test_generate_office_layout(
        self,
        orchestrator: LayoutOrchestrator,
        office_request: LayoutRequest,
    ) -> None:
        """Test generating an office layout."""
        response = await orchestrator.generate_layout(office_request)

        assert response.success is True
        assert response.output is not None

    @pytest.mark.asyncio
    async def test_generate_with_minimal_workflow(
        self,
        bedroom_request: LayoutRequest,
    ) -> None:
        """Test generating with minimal workflow."""
        config = OrchestratorConfig(use_minimal_workflow=True)
        orchestrator = LayoutOrchestrator(config)

        response = await orchestrator.generate_layout(bedroom_request)

        assert response.success is True

    @pytest.mark.asyncio
    async def test_phase_results_populated(
        self,
        orchestrator: LayoutOrchestrator,
        bedroom_request: LayoutRequest,
    ) -> None:
        """Test that phase results are populated."""
        response = await orchestrator.generate_layout(bedroom_request)

        assert len(response.phase_results) > 0
        # Check that phases were executed
        phases_executed = {r.phase for r in response.phase_results}
        assert AgentPhase.INITIALIZATION in phases_executed
        assert AgentPhase.SPATIAL_ANALYSIS in phases_executed

    @pytest.mark.asyncio
    async def test_output_has_furniture(
        self,
        orchestrator: LayoutOrchestrator,
        bedroom_request: LayoutRequest,
    ) -> None:
        """Test that output contains furniture."""
        response = await orchestrator.generate_layout(bedroom_request)

        assert response.output is not None
        assert len(response.output.furniture) > 0
        # Check furniture has required fields
        furniture = response.output.furniture[0]
        assert furniture.pos_x >= 0
        assert furniture.pos_z >= 0
        assert furniture.width > 0

    @pytest.mark.asyncio
    async def test_workflow_state(
        self,
        orchestrator: LayoutOrchestrator,
        bedroom_request: LayoutRequest,
    ) -> None:
        """Test workflow state tracking."""
        await orchestrator.generate_layout(bedroom_request)

        state = orchestrator.get_workflow_state()
        # After successful generation, should be at OUTPUT_GENERATION
        assert state.current_phase in (
            AgentPhase.OUTPUT_GENERATION,
            AgentPhase.COMPLETED,
        )


class TestLayoutOrchestratorEdgeCases:
    """Edge case tests for LayoutOrchestrator."""

    @pytest.mark.asyncio
    async def test_small_room(self) -> None:
        """Test with a very small room."""
        orchestrator = LayoutOrchestrator()
        request = LayoutRequest(
            room_type="bedroom",
            width=2.0,
            depth=2.0,
            max_furniture_items=2,
        )

        response = await orchestrator.generate_layout(request)
        # Should still succeed but may have fewer items
        assert response.success is True

    @pytest.mark.asyncio
    async def test_large_room(self) -> None:
        """Test with a large room."""
        orchestrator = LayoutOrchestrator()
        request = LayoutRequest(
            room_type="living_room",
            width=8.0,
            depth=6.0,
            max_furniture_items=10,
        )

        response = await orchestrator.generate_layout(request)
        assert response.success is True

    @pytest.mark.asyncio
    async def test_different_room_types(self) -> None:
        """Test generating layouts for different room types."""
        orchestrator = LayoutOrchestrator()
        room_types = ["bedroom", "office", "living_room"]

        for room_type in room_types:
            request = LayoutRequest(
                room_type=room_type,
                width=5.0,
                depth=4.0,
            )
            response = await orchestrator.generate_layout(request)
            assert response.success is True, f"Failed for {room_type}"


class TestGenerateLayoutFunction:
    """Tests for the generate_layout convenience function."""

    @pytest.mark.asyncio
    async def test_generate_layout_simple(self) -> None:
        """Test simple layout generation."""
        response = await generate_layout(
            room_type="bedroom",
            width=5.0,
            depth=4.0,
        )

        assert response.success is True
        assert response.furniture_count > 0

    @pytest.mark.asyncio
    async def test_generate_layout_with_options(self) -> None:
        """Test layout generation with options."""
        response = await generate_layout(
            room_type="office",
            width=4.0,
            depth=3.0,
            height=3.0,
            budget_level="high",
            max_furniture_items=5,
        )

        assert response.success is True


class TestLayoutOrchestratorScoring:
    """Tests for scoring in orchestrator."""

    @pytest.mark.asyncio
    async def test_feng_shui_score_included(self) -> None:
        """Test that feng shui score is included in response."""
        orchestrator = LayoutOrchestrator()
        request = LayoutRequest(
            room_type="bedroom",
            width=5.0,
            depth=4.0,
        )

        response = await orchestrator.generate_layout(request)

        assert response.success is True
        assert response.feng_shui_score > 0
        assert response.feng_shui_score <= 100

    @pytest.mark.asyncio
    async def test_score_breakdown_in_output(self) -> None:
        """Test that score breakdown is in output."""
        orchestrator = LayoutOrchestrator()
        request = LayoutRequest(
            room_type="bedroom",
            width=5.0,
            depth=4.0,
        )

        response = await orchestrator.generate_layout(request)

        assert response.output is not None
        breakdown = response.output.score_breakdown
        assert "command_position" in breakdown
        assert "five_elements" in breakdown
        assert "chi_flow" in breakdown
        assert "sha_chi_avoidance" in breakdown
