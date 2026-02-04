"""Agent state machine for feng shui layout generation."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from src.modules.layout.application.dtos import AgentContext, AgentPhase


class TransitionResult(str, Enum):
    """Result of a state transition."""

    SUCCESS = "success"
    FAILED = "failed"
    RETRY = "retry"
    SKIP = "skip"


@dataclass
class StateTransition:
    """A transition between agent states.

    Attributes:
        from_phase: Starting phase.
        to_phase: Target phase.
        condition: Optional condition function.
        on_transition: Optional callback on transition.
    """

    from_phase: AgentPhase
    to_phase: AgentPhase
    condition: Callable[[AgentContext], bool] | None = None
    on_transition: Callable[[AgentContext], None] | None = None

    def can_transition(self, context: AgentContext) -> bool:
        """Check if transition is allowed."""
        if self.condition is None:
            return True
        return self.condition(context)

    def execute(self, context: AgentContext) -> None:
        """Execute the transition callback if defined."""
        if self.on_transition:
            self.on_transition(context)


@dataclass
class PhaseConfig:
    """Configuration for a phase.

    Attributes:
        phase: The phase this config applies to.
        max_retries: Maximum retries for this phase.
        timeout_seconds: Timeout for this phase.
        required: Whether this phase is required.
        can_skip: Whether this phase can be skipped.
    """

    phase: AgentPhase
    max_retries: int = 3
    timeout_seconds: float = 30.0
    required: bool = True
    can_skip: bool = False


@dataclass
class PhaseResult:
    """Result of executing a phase.

    Attributes:
        phase: The phase that was executed.
        result: The transition result.
        error: Error message if failed.
        data: Any data produced by the phase.
        duration_ms: Execution duration in milliseconds.
    """

    phase: AgentPhase
    result: TransitionResult
    error: str | None = None
    data: dict[str, Any] = field(default_factory=dict)
    duration_ms: float = 0.0

    @property
    def is_success(self) -> bool:
        """Check if phase succeeded."""
        return self.result == TransitionResult.SUCCESS

    @property
    def should_retry(self) -> bool:
        """Check if phase should be retried."""
        return self.result == TransitionResult.RETRY


class AgentStateMachine:
    """State machine for managing agent workflow phases.

    This class manages the transitions between agent phases
    and tracks the overall workflow state.
    """

    # Valid phase transitions
    TRANSITIONS: dict[AgentPhase, list[AgentPhase]] = {
        AgentPhase.INITIALIZATION: [AgentPhase.INPUT_ANALYSIS, AgentPhase.FAILED],
        AgentPhase.INPUT_ANALYSIS: [
            AgentPhase.SPATIAL_ANALYSIS,
            AgentPhase.FAILED,
        ],
        AgentPhase.SPATIAL_ANALYSIS: [
            AgentPhase.RULE_RETRIEVAL,
            AgentPhase.FURNITURE_SELECTION,
            AgentPhase.FAILED,
        ],
        AgentPhase.RULE_RETRIEVAL: [
            AgentPhase.FURNITURE_SELECTION,
            AgentPhase.FAILED,
        ],
        AgentPhase.FURNITURE_SELECTION: [
            AgentPhase.PLACEMENT_PLANNING,
            AgentPhase.PLACEMENT_EXECUTION,  # Allow skipping planning in minimal workflow
            AgentPhase.FAILED,
        ],
        AgentPhase.PLACEMENT_PLANNING: [
            AgentPhase.PLACEMENT_EXECUTION,
            AgentPhase.FAILED,
        ],
        AgentPhase.PLACEMENT_EXECUTION: [
            AgentPhase.COLLISION_RESOLUTION,
            AgentPhase.SCORING,
            AgentPhase.FAILED,
        ],
        AgentPhase.COLLISION_RESOLUTION: [
            AgentPhase.PLACEMENT_EXECUTION,
            AgentPhase.SCORING,
            AgentPhase.FAILED,
        ],
        AgentPhase.SCORING: [
            AgentPhase.VALIDATION,
            AgentPhase.OUTPUT_GENERATION,  # Allow skipping validation in minimal workflow
            AgentPhase.PLACEMENT_EXECUTION,  # Retry if score too low
            AgentPhase.FAILED,
        ],
        AgentPhase.VALIDATION: [
            AgentPhase.OUTPUT_GENERATION,
            AgentPhase.SCORING,  # Re-score after fixes
            AgentPhase.FAILED,
        ],
        AgentPhase.OUTPUT_GENERATION: [
            AgentPhase.COMPLETED,
            AgentPhase.FAILED,
        ],
        AgentPhase.COMPLETED: [],
        AgentPhase.FAILED: [],
    }

    # Default phase configurations
    DEFAULT_CONFIGS: dict[AgentPhase, PhaseConfig] = {
        AgentPhase.INITIALIZATION: PhaseConfig(
            phase=AgentPhase.INITIALIZATION,
            max_retries=1,
            required=True,
        ),
        AgentPhase.INPUT_ANALYSIS: PhaseConfig(
            phase=AgentPhase.INPUT_ANALYSIS,
            max_retries=2,
            required=True,
        ),
        AgentPhase.SPATIAL_ANALYSIS: PhaseConfig(
            phase=AgentPhase.SPATIAL_ANALYSIS,
            max_retries=2,
            required=True,
        ),
        AgentPhase.RULE_RETRIEVAL: PhaseConfig(
            phase=AgentPhase.RULE_RETRIEVAL,
            max_retries=2,
            required=False,
            can_skip=True,
        ),
        AgentPhase.FURNITURE_SELECTION: PhaseConfig(
            phase=AgentPhase.FURNITURE_SELECTION,
            max_retries=3,
            required=True,
        ),
        AgentPhase.PLACEMENT_PLANNING: PhaseConfig(
            phase=AgentPhase.PLACEMENT_PLANNING,
            max_retries=2,
            required=True,
        ),
        AgentPhase.PLACEMENT_EXECUTION: PhaseConfig(
            phase=AgentPhase.PLACEMENT_EXECUTION,
            max_retries=3,
            timeout_seconds=60.0,
            required=True,
        ),
        AgentPhase.COLLISION_RESOLUTION: PhaseConfig(
            phase=AgentPhase.COLLISION_RESOLUTION,
            max_retries=5,
            required=False,
            can_skip=True,
        ),
        AgentPhase.SCORING: PhaseConfig(
            phase=AgentPhase.SCORING,
            max_retries=2,
            required=True,
        ),
        AgentPhase.VALIDATION: PhaseConfig(
            phase=AgentPhase.VALIDATION,
            max_retries=2,
            required=True,
        ),
        AgentPhase.OUTPUT_GENERATION: PhaseConfig(
            phase=AgentPhase.OUTPUT_GENERATION,
            max_retries=1,
            required=True,
        ),
    }

    def __init__(self) -> None:
        """Initialize the state machine."""
        self._phase_configs = dict(self.DEFAULT_CONFIGS)
        self._custom_transitions: list[StateTransition] = []
        self._phase_history: list[tuple[AgentPhase, TransitionResult]] = []
        self._retry_counts: dict[AgentPhase, int] = {}

    def can_transition(
        self,
        context: AgentContext,
        target_phase: AgentPhase,
    ) -> bool:
        """Check if transition to target phase is valid.

        Args:
            context: Current agent context.
            target_phase: Target phase to transition to.

        Returns:
            True if transition is valid.
        """
        current_phase = context.phase
        valid_targets = self.TRANSITIONS.get(current_phase, [])

        if target_phase not in valid_targets:
            return False

        # Check custom transition conditions
        for transition in self._custom_transitions:
            if (
                transition.from_phase == current_phase
                and transition.to_phase == target_phase
            ):
                if not transition.can_transition(context):
                    return False

        return True

    def transition(
        self,
        context: AgentContext,
        target_phase: AgentPhase,
        result: TransitionResult = TransitionResult.SUCCESS,
    ) -> bool:
        """Transition to a new phase.

        Args:
            context: Agent context to update.
            target_phase: Target phase.
            result: Result of the transition.

        Returns:
            True if transition succeeded.
        """
        if not self.can_transition(context, target_phase):
            return False

        # Execute custom transition callbacks
        for transition in self._custom_transitions:
            if (
                transition.from_phase == context.phase
                and transition.to_phase == target_phase
            ):
                transition.execute(context)

        # Record history
        self._phase_history.append((context.phase, result))

        # Update context
        context.advance_phase(target_phase)

        return True

    def get_next_phase(self, context: AgentContext) -> AgentPhase | None:
        """Get the next phase in the workflow.

        Args:
            context: Current agent context.

        Returns:
            Next phase, or None if no valid transition.
        """
        current_phase = context.phase
        valid_targets = self.TRANSITIONS.get(current_phase, [])

        # Filter out terminal states unless we're going there
        for target in valid_targets:
            if target not in (AgentPhase.COMPLETED, AgentPhase.FAILED):
                if self.can_transition(context, target):
                    return target

        return None

    def should_retry(self, context: AgentContext, phase: AgentPhase) -> bool:
        """Check if a phase should be retried.

        Args:
            context: Agent context.
            phase: Phase to check.

        Returns:
            True if phase should be retried.
        """
        config = self._phase_configs.get(phase)
        if config is None:
            return False

        retry_count = self._retry_counts.get(phase, 0)
        return retry_count < config.max_retries

    def record_retry(self, phase: AgentPhase) -> int:
        """Record a retry attempt for a phase.

        Args:
            phase: Phase being retried.

        Returns:
            Current retry count.
        """
        current = self._retry_counts.get(phase, 0)
        self._retry_counts[phase] = current + 1
        return self._retry_counts[phase]

    def reset_retries(self, phase: AgentPhase) -> None:
        """Reset retry count for a phase.

        Args:
            phase: Phase to reset.
        """
        self._retry_counts[phase] = 0

    def get_phase_config(self, phase: AgentPhase) -> PhaseConfig | None:
        """Get configuration for a phase.

        Args:
            phase: Phase to get config for.

        Returns:
            Phase configuration or None.
        """
        return self._phase_configs.get(phase)

    def set_phase_config(self, config: PhaseConfig) -> None:
        """Set configuration for a phase.

        Args:
            config: Phase configuration to set.
        """
        self._phase_configs[config.phase] = config

    def add_transition(self, transition: StateTransition) -> None:
        """Add a custom transition.

        Args:
            transition: Transition to add.
        """
        self._custom_transitions.append(transition)

    def get_phase_history(self) -> list[tuple[AgentPhase, TransitionResult]]:
        """Get the phase transition history.

        Returns:
            List of (phase, result) tuples.
        """
        return list(self._phase_history)

    def is_terminal(self, phase: AgentPhase) -> bool:
        """Check if phase is a terminal state.

        Args:
            phase: Phase to check.

        Returns:
            True if phase is terminal.
        """
        return phase in (AgentPhase.COMPLETED, AgentPhase.FAILED)

    def reset(self) -> None:
        """Reset the state machine."""
        self._phase_history.clear()
        self._retry_counts.clear()


@dataclass
class WorkflowState:
    """Current state of the agent workflow.

    Attributes:
        current_phase: Current phase.
        phase_history: History of phase transitions.
        retry_counts: Retry counts per phase.
        is_running: Whether workflow is running.
        is_completed: Whether workflow completed.
        is_failed: Whether workflow failed.
        error_message: Error message if failed.
    """

    current_phase: AgentPhase = AgentPhase.INITIALIZATION
    phase_history: list[AgentPhase] = field(default_factory=list)
    retry_counts: dict[str, int] = field(default_factory=dict)
    is_running: bool = False
    is_completed: bool = False
    is_failed: bool = False
    error_message: str | None = None

    @classmethod
    def from_context(cls, context: AgentContext) -> WorkflowState:
        """Create workflow state from agent context.

        Args:
            context: Agent context.

        Returns:
            WorkflowState instance.
        """
        return cls(
            current_phase=context.phase,
            is_completed=context.phase == AgentPhase.COMPLETED,
            is_failed=context.phase == AgentPhase.FAILED,
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "current_phase": self.current_phase.value,
            "phase_history": [p.value for p in self.phase_history],
            "retry_counts": self.retry_counts,
            "is_running": self.is_running,
            "is_completed": self.is_completed,
            "is_failed": self.is_failed,
            "error_message": self.error_message,
        }


def create_standard_workflow() -> list[AgentPhase]:
    """Create the standard workflow phase sequence.

    Returns:
        List of phases in execution order.
    """
    return [
        AgentPhase.INITIALIZATION,
        AgentPhase.INPUT_ANALYSIS,
        AgentPhase.SPATIAL_ANALYSIS,
        AgentPhase.RULE_RETRIEVAL,
        AgentPhase.FURNITURE_SELECTION,
        AgentPhase.PLACEMENT_PLANNING,
        AgentPhase.PLACEMENT_EXECUTION,
        AgentPhase.SCORING,
        AgentPhase.VALIDATION,
        AgentPhase.OUTPUT_GENERATION,
        AgentPhase.COMPLETED,
    ]


def create_minimal_workflow() -> list[AgentPhase]:
    """Create a minimal workflow (skip optional phases).

    Returns:
        List of required phases only.
    """
    return [
        AgentPhase.INITIALIZATION,
        AgentPhase.INPUT_ANALYSIS,
        AgentPhase.SPATIAL_ANALYSIS,
        AgentPhase.FURNITURE_SELECTION,
        AgentPhase.PLACEMENT_EXECUTION,
        AgentPhase.SCORING,
        AgentPhase.OUTPUT_GENERATION,
        AgentPhase.COMPLETED,
    ]
