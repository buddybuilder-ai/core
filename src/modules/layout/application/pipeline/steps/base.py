"""Base class for pipeline steps."""

from __future__ import annotations

import abc
import logging
import time
from collections.abc import AsyncGenerator

from src.modules.layout.application.pipeline.models import (
    PipelineConfig,
    PipelineState,
    PipelineStep,
    SSEEvent,
    SSEEventType,
    StepResult,
    StepStatus,
)

logger = logging.getLogger(__name__)


class BaseStep(abc.ABC):
    """Abstract base class for all pipeline steps."""

    step: PipelineStep

    def __init__(self, config: PipelineConfig) -> None:
        self.config = config

    @abc.abstractmethod
    async def execute(self, state: PipelineState) -> AsyncGenerator[SSEEvent, None]:
        """Execute the step, yielding SSE events as progress is made.

        Args:
            state: The mutable pipeline state.

        Yields:
            SSEEvent objects for streaming to client.
        """
        # pragma: no cover — abstract; yield makes this an async generator function
        yield  # type: ignore[misc]

    async def run(self, state: PipelineState) -> StepResult:
        """Run the step and collect the result.

        Wraps execute() with timing, error handling, and state updates.

        Args:
            state: The mutable pipeline state.

        Returns:
            StepResult with step outcome.
        """
        start = time.time()
        state.current_step = self.step
        result = StepResult(step=self.step, status=StepStatus.RUNNING)

        try:
            async for _ in self.execute(state):
                pass  # Events consumed by orchestrator's streaming path
            result.status = StepStatus.COMPLETED
        except Exception as e:
            logger.error(f"Step {self.step.value} failed: {e}")
            result.status = StepStatus.FAILED
            result.error = str(e)
        finally:
            result.duration_ms = (time.time() - start) * 1000

        state.step_results.append(result)
        return result

    def _emit_started(self) -> SSEEvent:
        return SSEEvent(
            event_type=SSEEventType.STEP_STARTED,
            data={"step": self.step.value},
        )

    def _emit_progress(self, message: str, progress: float = 0) -> SSEEvent:
        return SSEEvent(
            event_type=SSEEventType.STEP_PROGRESS,
            data={
                "step": self.step.value,
                "message": message,
                "progress": progress,
            },
        )

    def _emit_completed(self, data: dict[str, object] | None = None) -> SSEEvent:
        return SSEEvent(
            event_type=SSEEventType.STEP_COMPLETED,
            data={"step": self.step.value, **(data or {})},
        )

    def _emit_failed(self, error: str) -> SSEEvent:
        return SSEEvent(
            event_type=SSEEventType.STEP_FAILED,
            data={"step": self.step.value, "error": error},
        )
