"""Integration tests for feng shui layout generation."""

import pytest

from src.modules.layout.application.agent import (
    LayoutOrchestrator,
    LayoutRequest,
    OrchestratorConfig,
    generate_layout,
)
from src.modules.layout.application.dtos import AgentPhase
from tests.factories.layout_factories import LayoutRequestFactory, RoomFactory


class TestFengShuiLayoutGeneration:
    """Integration tests for complete layout generation flow."""

    @pytest.mark.asyncio
    async def test_bedroom_layout_generation(self) -> None:
        """Test generating a complete bedroom layout."""
        request = LayoutRequestFactory.create_bedroom_request()

        orchestrator = LayoutOrchestrator()
        response = await orchestrator.generate_layout(request)

        assert response.success is True
        assert response.output is not None
        assert response.furniture_count > 0
        assert response.feng_shui_score > 0
        assert response.execution_time_ms > 0

    @pytest.mark.asyncio
    async def test_office_layout_generation(self) -> None:
        """Test generating a complete office layout."""
        request = LayoutRequestFactory.create_office_request()

        orchestrator = LayoutOrchestrator()
        response = await orchestrator.generate_layout(request)

        assert response.success is True
        assert response.output is not None
        assert response.furniture_count > 0

    @pytest.mark.asyncio
    async def test_living_room_layout_generation(self) -> None:
        """Test generating a complete living room layout."""
        request = LayoutRequestFactory.create_living_room_request()

        orchestrator = LayoutOrchestrator()
        response = await orchestrator.generate_layout(request)

        assert response.success is True
        assert response.output is not None

    @pytest.mark.asyncio
    async def test_layout_with_doors_and_windows(self) -> None:
        """Test layout generation with door and window specifications."""
        request = LayoutRequestFactory.create_request_with_doors_and_windows()

        orchestrator = LayoutOrchestrator()
        response = await orchestrator.generate_layout(request)

        assert response.success is True
        assert response.output is not None


class TestLayoutGenerationWorkflow:
    """Tests for the complete workflow execution."""

    @pytest.mark.asyncio
    async def test_all_phases_executed(self) -> None:
        """Test that all workflow phases are executed."""
        request = LayoutRequestFactory.create_bedroom_request()

        orchestrator = LayoutOrchestrator()
        response = await orchestrator.generate_layout(request)

        assert response.success is True

        # Check that multiple phases were executed
        phases_executed = {r.phase for r in response.phase_results}
        assert AgentPhase.INITIALIZATION in phases_executed
        assert AgentPhase.SPATIAL_ANALYSIS in phases_executed
        assert AgentPhase.FURNITURE_SELECTION in phases_executed
        assert AgentPhase.PLACEMENT_EXECUTION in phases_executed
        assert AgentPhase.SCORING in phases_executed

    @pytest.mark.asyncio
    async def test_minimal_workflow(self) -> None:
        """Test minimal workflow execution."""
        request = LayoutRequestFactory.create_bedroom_request()
        config = OrchestratorConfig(use_minimal_workflow=True)

        orchestrator = LayoutOrchestrator(config)
        response = await orchestrator.generate_layout(request)

        assert response.success is True
        assert response.furniture_count > 0

    @pytest.mark.asyncio
    async def test_workflow_state_tracking(self) -> None:
        """Test that workflow state is properly tracked."""
        request = LayoutRequestFactory.create_bedroom_request()

        orchestrator = LayoutOrchestrator()
        await orchestrator.generate_layout(request)

        state = orchestrator.get_workflow_state()
        # After successful generation, should be at OUTPUT_GENERATION or COMPLETED
        assert state.current_phase in (
            AgentPhase.OUTPUT_GENERATION,
            AgentPhase.COMPLETED,
        )


class TestFengShuiScoring:
    """Tests for feng shui scoring in integration."""

    @pytest.mark.asyncio
    async def test_score_within_valid_range(self) -> None:
        """Test that feng shui score is within valid range."""
        request = LayoutRequestFactory.create_bedroom_request()

        orchestrator = LayoutOrchestrator()
        response = await orchestrator.generate_layout(request)

        assert response.success is True
        assert 0 <= response.feng_shui_score <= 100

    @pytest.mark.asyncio
    async def test_score_breakdown_available(self) -> None:
        """Test that score breakdown is available in output."""
        request = LayoutRequestFactory.create_bedroom_request()

        orchestrator = LayoutOrchestrator()
        response = await orchestrator.generate_layout(request)

        assert response.success is True
        assert response.output is not None
        assert response.output.score_breakdown is not None

        breakdown = response.output.score_breakdown
        assert "command_position" in breakdown
        assert "five_elements" in breakdown
        assert "chi_flow" in breakdown
        assert "sha_chi_avoidance" in breakdown

    @pytest.mark.asyncio
    async def test_acceptable_score_threshold(self) -> None:
        """Test that generated layouts meet minimum acceptable score."""
        request = LayoutRequestFactory.create_bedroom_request()
        config = OrchestratorConfig(
            min_acceptable_score=30,
            auto_retry_low_score=False,
        )

        orchestrator = LayoutOrchestrator(config)
        response = await orchestrator.generate_layout(request)

        assert response.success is True
        # Score should typically be above minimum
        assert response.feng_shui_score >= 30


class TestFurniturePlacement:
    """Tests for furniture placement in integration."""

    @pytest.mark.asyncio
    async def test_essential_furniture_placed(self) -> None:
        """Test that essential furniture is placed."""
        request = LayoutRequestFactory.create_bedroom_request()

        orchestrator = LayoutOrchestrator()
        response = await orchestrator.generate_layout(request)

        assert response.success is True
        assert response.output is not None

        # Should have at least one essential item (bed)
        essential_items = [
            f for f in response.output.furniture if f.is_essential
        ]
        assert len(essential_items) > 0

    @pytest.mark.asyncio
    async def test_furniture_positions_valid(self) -> None:
        """Test that furniture positions are within room bounds."""
        request = LayoutRequestFactory.create_bedroom_request(
            width=5.0,
            depth=4.0,
        )

        orchestrator = LayoutOrchestrator()
        response = await orchestrator.generate_layout(request)

        assert response.success is True
        assert response.output is not None

        for furniture in response.output.furniture:
            # Position should be within room
            assert furniture.pos_x >= 0
            assert furniture.pos_z >= 0
            assert furniture.pos_x + furniture.width <= 5.0 + 0.1  # Small tolerance
            assert furniture.pos_z + furniture.depth <= 4.0 + 0.1

    @pytest.mark.asyncio
    async def test_furniture_no_overlaps(self) -> None:
        """Test that placed furniture doesn't overlap."""
        request = LayoutRequestFactory.create_bedroom_request()

        orchestrator = LayoutOrchestrator()
        response = await orchestrator.generate_layout(request)

        assert response.success is True
        assert response.output is not None

        furniture_list = response.output.furniture
        for i, f1 in enumerate(furniture_list):
            for f2 in furniture_list[i + 1:]:
                # Check for overlaps (AABB collision)
                # Account for rotation
                f1_width = f1.depth if f1.rotation in (90, 270) else f1.width
                f1_depth = f1.width if f1.rotation in (90, 270) else f1.depth
                f2_width = f2.depth if f2.rotation in (90, 270) else f2.width
                f2_depth = f2.width if f2.rotation in (90, 270) else f2.depth

                overlaps_x = not (
                    f1.pos_x + f1_width <= f2.pos_x
                    or f2.pos_x + f2_width <= f1.pos_x
                )
                overlaps_z = not (
                    f1.pos_z + f1_depth <= f2.pos_z
                    or f2.pos_z + f2_depth <= f1.pos_z
                )

                if overlaps_x and overlaps_z:
                    pytest.fail(
                        f"Furniture overlap detected between {f1.name} and {f2.name}"
                    )


class TestLayoutOutput:
    """Tests for layout output generation."""

    @pytest.mark.asyncio
    async def test_output_has_required_fields(self) -> None:
        """Test that output has all required fields."""
        request = LayoutRequestFactory.create_bedroom_request()

        orchestrator = LayoutOrchestrator()
        response = await orchestrator.generate_layout(request)

        assert response.success is True
        assert response.output is not None

        output = response.output
        assert output.room_type is not None
        assert output.feng_shui_score is not None
        assert output.furniture is not None
        assert output.score_breakdown is not None

    @pytest.mark.asyncio
    async def test_output_to_dict(self) -> None:
        """Test that output can be serialized to dict."""
        request = LayoutRequestFactory.create_bedroom_request()

        orchestrator = LayoutOrchestrator()
        response = await orchestrator.generate_layout(request)

        assert response.success is True
        assert response.output is not None

        output_dict = response.output.to_dict()
        assert isinstance(output_dict, dict)
        assert "room_type" in output_dict
        assert "feng_shui_score" in output_dict
        assert "furniture" in output_dict

    @pytest.mark.asyncio
    async def test_response_to_dict(self) -> None:
        """Test that response can be serialized to dict."""
        request = LayoutRequestFactory.create_bedroom_request()

        orchestrator = LayoutOrchestrator()
        response = await orchestrator.generate_layout(request)

        response_dict = response.to_dict()
        assert isinstance(response_dict, dict)
        assert "success" in response_dict
        assert "feng_shui_score" in response_dict


class TestConvenienceFunction:
    """Tests for the generate_layout convenience function."""

    @pytest.mark.asyncio
    async def test_generate_layout_simple(self) -> None:
        """Test simple layout generation via convenience function."""
        response = await generate_layout(
            room_type="bedroom",
            width=5.0,
            depth=4.0,
        )

        assert response.success is True
        assert response.furniture_count > 0

    @pytest.mark.asyncio
    async def test_generate_layout_with_options(self) -> None:
        """Test layout generation with all options."""
        response = await generate_layout(
            room_type="office",
            width=4.0,
            depth=3.0,
            height=3.0,
            budget_level="high",
            max_furniture_items=5,
        )

        assert response.success is True


class TestEdgeCases:
    """Edge case tests for layout generation."""

    @pytest.mark.asyncio
    async def test_small_room_layout(self) -> None:
        """Test layout generation for a very small room."""
        request = LayoutRequest(
            room_type="bedroom",
            width=2.5,
            depth=2.5,
            max_furniture_items=3,
        )

        orchestrator = LayoutOrchestrator()
        response = await orchestrator.generate_layout(request)

        # Should succeed but may have limited furniture
        assert response.success is True

    @pytest.mark.asyncio
    async def test_large_room_layout(self) -> None:
        """Test layout generation for a large room."""
        request = LayoutRequest(
            room_type="living_room",
            width=8.0,
            depth=6.0,
            max_furniture_items=10,
        )

        orchestrator = LayoutOrchestrator()
        response = await orchestrator.generate_layout(request)

        assert response.success is True
        assert response.furniture_count > 0

    @pytest.mark.asyncio
    async def test_different_budget_levels(self) -> None:
        """Test layout generation with different budget levels."""
        for budget in ["low", "medium", "high"]:
            request = LayoutRequest(
                room_type="bedroom",
                width=5.0,
                depth=4.0,
                budget_level=budget,
            )

            orchestrator = LayoutOrchestrator()
            response = await orchestrator.generate_layout(request)

            assert response.success is True, f"Failed for budget: {budget}"

    @pytest.mark.asyncio
    async def test_all_room_types(self) -> None:
        """Test layout generation for all supported room types."""
        room_types = ["bedroom", "office", "living_room"]

        for room_type in room_types:
            request = LayoutRequest(
                room_type=room_type,
                width=5.0,
                depth=4.0,
            )

            orchestrator = LayoutOrchestrator()
            response = await orchestrator.generate_layout(request)

            assert response.success is True, f"Failed for room type: {room_type}"


class TestPerformance:
    """Performance-related integration tests."""

    @pytest.mark.asyncio
    async def test_layout_generation_completes(self) -> None:
        """Test that layout generation completes within timeout."""
        request = LayoutRequestFactory.create_bedroom_request()
        config = OrchestratorConfig(timeout_seconds=30.0)

        orchestrator = LayoutOrchestrator(config)
        response = await orchestrator.generate_layout(request)

        assert response.success is True
        # Should complete well under timeout
        assert response.execution_time_ms < 30000  # 30 seconds

    @pytest.mark.asyncio
    async def test_multiple_sequential_layouts(self) -> None:
        """Test generating multiple layouts sequentially."""
        requests = [
            LayoutRequestFactory.create_bedroom_request(),
            LayoutRequestFactory.create_office_request(),
            LayoutRequestFactory.create_living_room_request(),
        ]

        for request in requests:
            orchestrator = LayoutOrchestrator()
            response = await orchestrator.generate_layout(request)
            assert response.success is True
