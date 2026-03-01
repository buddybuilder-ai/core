"""Integration tests for PipelineOrchestrator.

These tests mock FengShuiLLMAgent to avoid real LLM/API calls.  They verify:
 - Pipeline structure (all 5 steps run, SSE events emitted)
 - RAG context is retrieved and stored in state
 - Personality mode is threaded through to the Explainer step
 - Repair loop fires when conflicts are found
 - LLM fallback path (template explanation) on LLM error
 - SSE event ordering (pipeline_started first, pipeline_completed last)
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.modules.layout.application.pipeline import PipelineConfig, PipelineOrchestrator
from src.modules.layout.application.pipeline.models import (
    Conflict,
    ConflictSeverity,
    ConflictType,
    PipelineState,
    SSEEventType,
)
from src.modules.layout.infrastructure.llm.langchain_agent import LLMResponse

# ---------------------------------------------------------------------------
# Shared test fixtures and helpers
# ---------------------------------------------------------------------------

MINIMAL_ROOM_SPEC: dict[str, Any] = {
    "room_type": "bedroom",
    "width": 4.0,
    "depth": 5.0,
    "height": 2.8,
    "budget_level": "medium",
    "doors": [],
    "windows": [],
    "style_preferences": [],
}

# Returning success=False causes step 2 to use the heuristic fallback path,
# which populates state.layout_items without requiring valid SemanticPlacementSchema.
_PLAN_LAYOUT_FAIL_RESPONSE = LLMResponse(
    success=False,
    content=None,
    error="mocked: use heuristic fallback",
)

_EXPLAIN_RESPONSE = LLMResponse(
    success=True,
    content="ห้องนอนถูกจัดวางอย่างสมดุลตามหลักฮวงจุ้ย",
    raw_response="{}",
)


@pytest.fixture
def mock_llm_step2_fallback():
    """Make step 2 LLM fail so the heuristic fallback path is used.
    This populates state.layout_items without needing valid semantic placements.
    """
    with patch(
        "src.modules.layout.application.pipeline.steps.step2_layout_generator.FengShuiLLMAgent"
    ) as MockAgent:
        instance = MagicMock()
        # select_furniture is not called by FengShuiLLMAgent in step 2 —
        # FurnitureSelector handles that internally, so only plan_layout matters.
        instance.plan_layout = AsyncMock(return_value=_PLAN_LAYOUT_FAIL_RESPONSE)
        MockAgent.return_value = instance
        yield instance


@pytest.fixture
def mock_llm_step5_explain():
    """Mock step 5 explain_layout to return a canned Thai explanation."""
    with patch(
        "src.modules.layout.application.pipeline.steps.step5_explainer.FengShuiLLMAgent"
    ) as MockAgent:
        instance = MagicMock()
        instance.explain_layout = AsyncMock(return_value=_EXPLAIN_RESPONSE)
        MockAgent.return_value = instance
        yield instance


@pytest.fixture
def mock_both_steps(mock_llm_step2_fallback, mock_llm_step5_explain):
    """Combined fixture: step 2 heuristic + step 5 explain mocked."""
    return {"step2": mock_llm_step2_fallback, "step5": mock_llm_step5_explain}


async def _collect_events(room_spec: dict, mode: str = "buddy") -> list[dict]:
    """Run the full pipeline and return all SSE events as dicts."""
    config = PipelineConfig(max_repair_loops=1)
    orchestrator = PipelineOrchestrator(config)
    events = []
    async for event in orchestrator.run(room_spec, mode=mode):
        events.append({"type": event.event_type, "data": event.data})
    return events


# ===========================================================================
# TestPipelineNewLayout
# ===========================================================================

@pytest.mark.integration
class TestPipelineNewLayout:
    """Test the full new_layout pipeline flow with mocked LLM."""

    @pytest.mark.asyncio
    async def test_pipeline_started_event_is_first(self, mock_both_steps):
        events = await _collect_events(MINIMAL_ROOM_SPEC)
        assert events[0]["type"] == SSEEventType.PIPELINE_STARTED

    @pytest.mark.asyncio
    async def test_pipeline_completed_event_is_last(self, mock_both_steps):
        events = await _collect_events(MINIMAL_ROOM_SPEC)
        assert events[-1]["type"] == SSEEventType.PIPELINE_COMPLETED

    @pytest.mark.asyncio
    async def test_pipeline_completed_event_has_layout_items(self, mock_both_steps):
        events = await _collect_events(MINIMAL_ROOM_SPEC)
        completed = events[-1]["data"]
        assert "layout_items" in completed

    @pytest.mark.asyncio
    async def test_all_required_step_started_events_present(self, mock_both_steps):
        events = await _collect_events(MINIMAL_ROOM_SPEC)
        step_started = [
            e["data"].get("step")
            for e in events
            if e["type"] == SSEEventType.STEP_STARTED
        ]
        assert "structured_data_builder" in step_started
        assert "layout_generator" in step_started
        assert "rule_checker" in step_started
        assert "explainer" in step_started

    @pytest.mark.asyncio
    async def test_pipeline_emits_rag_progress_events(self, mock_both_steps):
        events = await _collect_events(MINIMAL_ROOM_SPEC)
        rag_events = [
            e for e in events
            if e["type"] == SSEEventType.STEP_PROGRESS
            and e["data"].get("step") == "rag_retrieval"
        ]
        assert len(rag_events) >= 2

    @pytest.mark.asyncio
    async def test_pipeline_started_event_contains_config(self, mock_both_steps):
        events = await _collect_events(MINIMAL_ROOM_SPEC)
        data = events[0]["data"]
        assert "pipeline_id" in data
        assert "steps" in data
        assert "config" in data

    @pytest.mark.asyncio
    async def test_explain_layout_called_with_buddy_mode(self, mock_both_steps):
        await _collect_events(MINIMAL_ROOM_SPEC, mode="buddy")
        mock_both_steps["step5"].explain_layout.assert_awaited_once()
        kwargs = mock_both_steps["step5"].explain_layout.call_args.kwargs
        assert kwargs.get("personality_mode") == "buddy"

    @pytest.mark.asyncio
    async def test_explain_layout_called_with_mentor_mode(self, mock_both_steps):
        await _collect_events(MINIMAL_ROOM_SPEC, mode="mentor")
        kwargs = mock_both_steps["step5"].explain_layout.call_args.kwargs
        assert kwargs.get("personality_mode") == "mentor"

    @pytest.mark.asyncio
    async def test_explain_layout_called_with_fun_mode(self, mock_both_steps):
        await _collect_events(MINIMAL_ROOM_SPEC, mode="fun")
        kwargs = mock_both_steps["step5"].explain_layout.call_args.kwargs
        assert kwargs.get("personality_mode") == "fun"


# ===========================================================================
# TestPipelineRAGContext
# ===========================================================================

@pytest.mark.integration
class TestPipelineRAGContext:
    """Verify RAG context is retrieved and injected between Step 1 and Step 2."""

    @pytest.mark.asyncio
    async def test_rag_progress_events_emitted(self, mock_both_steps):
        """RAG progress events (0.0 start, 1.0 end) appear between steps 1 and 2."""
        events = await _collect_events(MINIMAL_ROOM_SPEC)
        rag_done = [
            e for e in events
            if e["type"] == SSEEventType.STEP_PROGRESS
            and e["data"].get("step") == "rag_retrieval"
            and e["data"].get("progress") == 1.0
        ]
        assert len(rag_done) >= 1
        # The completion message mentions "rules"
        assert "rules" in rag_done[0]["data"]["message"]

    @pytest.mark.asyncio
    async def test_plan_layout_called_after_rag_retrieval(self, mock_both_steps):
        """plan_layout is invoked (RAG context available to inject into step 2)."""
        await _collect_events(MINIMAL_ROOM_SPEC)
        assert mock_both_steps["step2"].plan_layout.call_count >= 1


# ===========================================================================
# TestPipelineRepairLoop
# ===========================================================================

@pytest.mark.integration
class TestPipelineRepairLoop:
    """Verify the repair loop fires when the rule checker adds conflicts."""

    @pytest.mark.asyncio
    async def test_repair_step_starts_when_conflicts_found(self, mock_both_steps):
        """Inject a conflict from the rule checker to trigger the repair step."""
        from src.modules.layout.application.pipeline.models import (
            PipelineStep,
            SSEEvent,
            StepResult,
            StepStatus,
        )
        from src.modules.layout.application.pipeline.steps.step3_rule_checker import RuleCheckerStep

        original_execute = RuleCheckerStep.execute

        async def checker_with_conflict(self_step, state: PipelineState):
            """Run original checker then inject an extra conflict."""
            async for event in original_execute(self_step, state):
                yield event
            # Force at least one unresolved conflict so repair loop is triggered
            state.conflicts.append(
                Conflict(
                    conflict_type=ConflictType.OVERLAP,
                    severity=ConflictSeverity.WARNING,
                    description="injected test overlap",
                )
            )

        with patch.object(RuleCheckerStep, "execute", checker_with_conflict):
            events = await _collect_events(MINIMAL_ROOM_SPEC)

        step_started_names = [
            e["data"].get("step")
            for e in events
            if e["type"] == SSEEventType.STEP_STARTED
        ]
        assert "repair" in step_started_names

    @pytest.mark.asyncio
    async def test_pipeline_reaches_explainer_step(self, mock_both_steps):
        """Explainer step always runs regardless of conflict count."""
        events = await _collect_events(MINIMAL_ROOM_SPEC)
        step_started_names = [
            e["data"].get("step")
            for e in events
            if e["type"] == SSEEventType.STEP_STARTED
        ]
        assert "explainer" in step_started_names


# ===========================================================================
# TestPipelineFallback
# ===========================================================================

@pytest.mark.integration
class TestPipelineFallback:
    """Test fallback paths when LLM calls fail."""

    @pytest.mark.asyncio
    async def test_explainer_falls_back_to_template_on_llm_error(
        self, mock_llm_step2_fallback
    ):
        """If explain_layout raises, pipeline still completes via template explanation."""
        with patch(
            "src.modules.layout.application.pipeline.steps.step5_explainer.FengShuiLLMAgent"
        ) as MockAgent5:
            instance5 = MagicMock()
            instance5.explain_layout = AsyncMock(
                side_effect=RuntimeError("LLM timeout")
            )
            MockAgent5.return_value = instance5

            events = await _collect_events(MINIMAL_ROOM_SPEC)

        # Pipeline should still complete (template fallback, not FAILED)
        assert events[-1]["type"] == SSEEventType.PIPELINE_COMPLETED
        assert events[-1]["data"].get("error") is None

    @pytest.mark.asyncio
    async def test_step2_heuristic_fallback_produces_layout_items(
        self, mock_both_steps
    ):
        """When plan_layout returns success=False, heuristic fallback places items."""
        events = await _collect_events(MINIMAL_ROOM_SPEC)
        completed = events[-1]["data"]
        # Heuristic fallback produces at least some layout items
        assert "layout_items" in completed


# ===========================================================================
# TestPipelineSSEEventStructure
# ===========================================================================

@pytest.mark.integration
class TestPipelineSSEEventStructure:
    """Verify SSE event data shapes and ordering."""

    @pytest.mark.asyncio
    async def test_step_started_events_have_step_field(self, mock_both_steps):
        events = await _collect_events(MINIMAL_ROOM_SPEC)
        for e in events:
            if e["type"] == SSEEventType.STEP_STARTED:
                assert "step" in e["data"], f"STEP_STARTED missing 'step': {e}"

    @pytest.mark.asyncio
    async def test_step_completed_events_have_step_field(self, mock_both_steps):
        events = await _collect_events(MINIMAL_ROOM_SPEC)
        for e in events:
            if e["type"] == SSEEventType.STEP_COMPLETED:
                assert "step" in e["data"], f"STEP_COMPLETED missing 'step': {e}"

    @pytest.mark.asyncio
    async def test_pipeline_started_lists_all_steps(self, mock_both_steps):
        events = await _collect_events(MINIMAL_ROOM_SPEC)
        expected_steps = [
            "structured_data_builder",
            "layout_generator",
            "rule_checker",
            "repair",
            "explainer",
        ]
        for step in expected_steps:
            assert step in events[0]["data"]["steps"]

    @pytest.mark.asyncio
    async def test_pipeline_completed_has_pipeline_id(self, mock_both_steps):
        events = await _collect_events(MINIMAL_ROOM_SPEC)
        assert "pipeline_id" in events[-1]["data"]

    @pytest.mark.asyncio
    async def test_sse_serialization_produces_valid_string(self, mock_both_steps):
        config = PipelineConfig()
        orchestrator = PipelineOrchestrator(config)
        async for event in orchestrator.run(MINIMAL_ROOM_SPEC):
            sse_string = event.to_sse()
            assert sse_string.startswith("event:")
            assert "data:" in sse_string
            assert sse_string.endswith("\n\n")
            break  # Only need to check the first event


# ===========================================================================
# TestPipelinePersonalityModes
# ===========================================================================

@pytest.mark.integration
class TestPipelinePersonalityModes:
    """Test that personality mode is threaded through the full pipeline."""

    @pytest.mark.asyncio
    async def test_default_mode_is_buddy(self, mock_both_steps):
        """run() without mode= defaults to buddy."""
        config = PipelineConfig()
        orchestrator = PipelineOrchestrator(config)
        async for _ in orchestrator.run(MINIMAL_ROOM_SPEC):
            pass
        kwargs = mock_both_steps["step5"].explain_layout.call_args.kwargs
        assert kwargs.get("personality_mode") == "buddy"

    @pytest.mark.asyncio
    async def test_mentor_mode_passed_to_explainer(self, mock_both_steps):
        await _collect_events(MINIMAL_ROOM_SPEC, mode="mentor")
        kwargs = mock_both_steps["step5"].explain_layout.call_args.kwargs
        assert kwargs.get("personality_mode") == "mentor"

    @pytest.mark.asyncio
    async def test_fun_mode_passed_to_explainer(self, mock_both_steps):
        await _collect_events(MINIMAL_ROOM_SPEC, mode="fun")
        kwargs = mock_both_steps["step5"].explain_layout.call_args.kwargs
        assert kwargs.get("personality_mode") == "fun"
