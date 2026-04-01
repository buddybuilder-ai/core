"""Pipeline Orchestrator — LLM-driven 5-step agentic pipeline.

Coordinates all 5 steps:
    1. Structured Data Builder
    2. Layout Generator (Planner)
    3. Rule Checker (Dual-rule)
    4. Repair (Auto-fix) ↺ loops to Step 3 if conflicts remain
    5. Explainer

Streams SSE events for real-time frontend updates.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from typing import Any

from src.modules.layout.application.pipeline.models import (
    PipelineConfig,
    PipelineResult,
    PipelineState,
    PipelineStep,
    SSEEvent,
    SSEEventType,
    StepStatus,
)
from src.modules.layout.application.pipeline.steps import (
    ExplainerStep,
    LayoutGeneratorStep,
    RepairStep,
    RuleCheckerStep,
    StructuredDataBuilderStep,
)

logger = logging.getLogger(__name__)


class PipelineOrchestrator:
    """Orchestrates the 5-step agentic layout pipeline.

    The orchestrator drives a fixed pipeline (1→2→3→4→5) with a
    configurable repair loop between steps 3 and 4 when conflicts
    are detected. Each step yields SSE events for streaming.
    """

    def __init__(self, config: PipelineConfig | None = None) -> None:
        self.config = config or PipelineConfig()

    async def run(
        self, room_spec: dict[str, Any], mode: str = "buddy"
    ) -> AsyncGenerator[SSEEvent, None]:
        """Run the full pipeline, yielding SSE events.

        This is the primary entry point for streaming mode.

        Args:
            room_spec: Raw room specification from the user/frontend.
            mode: Personality mode for Step 5 Explainer ("buddy"|"mentor"|"fun").

        Yields:
            SSEEvent objects to stream to the client.
        """
        state = PipelineState(room_spec=room_spec, personality_mode=mode)
        steps = self._build_steps()

        yield SSEEvent(
            event_type=SSEEventType.PIPELINE_STARTED,
            data={
                "pipeline_id": state.pipeline_id,
                "steps": [s.value for s in PipelineStep],
                "config": self.config.to_dict(),
            },
        )

        try:
            # Step 1: Structured Data Builder
            async for event in steps["data_builder"].execute(state):
                yield event
            self._check_step_ok(state, PipelineStep.STRUCTURED_DATA_BUILDER)

            # RAG retrieval — between Step 1 and Step 2
            # Graceful: ContextInjector never raises; empty context is a no-op
            from src.modules.layout.application.services import ContextInjector

            yield SSEEvent(
                event_type=SSEEventType.STEP_PROGRESS,
                data={
                    "step": "rag_retrieval",
                    "message": "Retrieving feng shui knowledge...",
                    "progress": 0.0,
                },
            )
            _injector = ContextInjector()
            _rag = await _injector.retrieve(state.room_spec)
            state.rag_context = {
                "layout_prompt_context": _rag.layout_prompt_context,
                "rule_descriptions": _rag.rule_descriptions,
                "source_citations": _rag.source_citations,
                "rules_retrieved": len(_rag.rules),
            }
            logger.info(f"RAG retrieval: {len(_rag.rules)} rules retrieved for pipeline")
            yield SSEEvent(
                event_type=SSEEventType.STEP_PROGRESS,
                data={
                    "step": "rag_retrieval",
                    "message": f"Retrieved {len(_rag.rules)} feng shui rules",
                    "progress": 1.0,
                },
            )

            # Step 2: Layout Generator
            async for event in steps["layout_generator"].execute(state):
                yield event
            self._check_step_ok(state, PipelineStep.LAYOUT_GENERATOR)

            # Step 3-4 Loop: Rule Check → Repair
            for iteration in range(self.config.max_repair_loops + 1):
                state.repair_iteration = iteration

                # Step 3: Rule Checker
                async for event in steps["rule_checker"].execute(state):
                    yield event
                self._check_step_ok(state, PipelineStep.RULE_CHECKER)

                # If no unresolved conflicts, break
                if not state.unresolved_conflicts:
                    logger.info(f"No conflicts after iteration {iteration} — skipping repair")
                    break

                # Last iteration? Don't repair, just report
                if iteration >= self.config.max_repair_loops:
                    logger.warning(
                        f"Max repair loops ({self.config.max_repair_loops}) "
                        f"reached with {len(state.unresolved_conflicts)} "
                        f"remaining conflicts"
                    )
                    break

                # Step 4: Repair
                async for event in steps["repair"].execute(state):
                    yield event

                # Always re-run Step 3 after repair to catch NEW collisions
                # introduced by shifting furniture (e.g., item A shifted onto
                # item C that was not involved in the original conflict).
                # The loop naturally breaks at the top if Step 3 finds zero
                # unresolved conflicts.

            # Step 5: Explainer
            async for event in steps["explainer"].execute(state):
                yield event

            # Pipeline complete
            result = self._build_result(state, success=True)
            yield SSEEvent(
                event_type=SSEEventType.PIPELINE_COMPLETED,
                data=result.to_dict(),
            )

        except Exception as e:
            logger.error(f"Pipeline failed: {e}")
            result = self._build_result(state, success=False, error=str(e))
            yield SSEEvent(
                event_type=SSEEventType.PIPELINE_FAILED,
                data={"error": str(e), "pipeline_id": state.pipeline_id},
            )

    async def run_sync(self, room_spec: dict[str, Any], mode: str = "buddy") -> PipelineResult:
        """Run the pipeline and return the final result (non-streaming).

        Args:
            room_spec: Raw room specification.
            mode: Personality mode for Step 5 Explainer ("buddy"|"mentor"|"fun").

        Returns:
            PipelineResult with the complete layout.
        """
        state = PipelineState(room_spec=room_spec, personality_mode=mode)
        last_event: SSEEvent | None = None

        async for event in self.run(room_spec, mode=mode):
            last_event = event

        if last_event and last_event.event_type == SSEEventType.PIPELINE_COMPLETED:
            return self._build_result(state, success=True)
        else:
            error = last_event.data.get("error", "Unknown") if last_event else "No events"
            return self._build_result(state, success=False, error=error)

    def _build_steps(self) -> dict[str, Any]:
        return {
            "data_builder": StructuredDataBuilderStep(self.config),
            "layout_generator": LayoutGeneratorStep(self.config),
            "rule_checker": RuleCheckerStep(self.config),
            "repair": RepairStep(self.config),
            "explainer": ExplainerStep(self.config),
        }

    def _check_step_ok(self, state: PipelineState, step: PipelineStep) -> None:
        """Check if the last step result was OK."""
        if state.step_results:
            last = state.step_results[-1]
            if last.step == step and last.status == StepStatus.FAILED:
                raise RuntimeError(f"Step {step.value} failed: {last.error}")

    def _build_result(
        self,
        state: PipelineState,
        success: bool,
        error: str | None = None,
    ) -> PipelineResult:
        return PipelineResult(
            success=success,
            pipeline_id=state.pipeline_id,
            layout_items=state.layout_items,
            feng_shui_score=state.feng_shui_score,
            conflicts=state.conflicts,
            repair_actions=state.repair_actions,
            explanation=state.explanation,
            step_results=state.step_results,
            total_duration_ms=state.elapsed_ms,
            error=error,
        )
