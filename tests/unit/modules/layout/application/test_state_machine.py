"""Tests for agent state machine."""

import pytest

from src.modules.layout.application.agent.state_machine import (
    AgentStateMachine,
    PhaseConfig,
    PhaseResult,
    StateTransition,
    TransitionResult,
    WorkflowState,
    create_minimal_workflow,
    create_standard_workflow,
)
from src.modules.layout.application.dtos import AgentContext, AgentPhase
from src.modules.layout.domain.entities import Room, RoomType


class TestTransitionResult:
    """Tests for TransitionResult enum."""

    def test_result_values(self) -> None:
        """Test transition result values."""
        assert TransitionResult.SUCCESS.value == "success"
        assert TransitionResult.FAILED.value == "failed"
        assert TransitionResult.RETRY.value == "retry"
        assert TransitionResult.SKIP.value == "skip"


class TestStateTransition:
    """Tests for StateTransition."""

    def test_transition_creation(self) -> None:
        """Test creating a state transition."""
        transition = StateTransition(
            from_phase=AgentPhase.INITIALIZATION,
            to_phase=AgentPhase.INPUT_ANALYSIS,
        )
        assert transition.from_phase == AgentPhase.INITIALIZATION
        assert transition.to_phase == AgentPhase.INPUT_ANALYSIS

    def test_transition_with_condition(self) -> None:
        """Test transition with condition function."""
        transition = StateTransition(
            from_phase=AgentPhase.SCORING,
            to_phase=AgentPhase.COMPLETED,
            condition=lambda ctx: ctx.feng_shui_score is not None,
        )

        room = Room(width=5.0, depth=4.0, height=2.8, room_type=RoomType.BEDROOM)
        context = AgentContext(room=room, room_type="bedroom")

        # Without score, condition should fail
        assert transition.can_transition(context) is False

        # With score, condition should pass
        from src.modules.layout.domain.value_objects import FengShuiScore

        context.feng_shui_score = FengShuiScore(
            command_position=20,
            five_elements=15,
            chi_flow=20,
            sha_chi_avoidance=20,
        )
        assert transition.can_transition(context) is True

    def test_transition_callback(self) -> None:
        """Test transition callback execution."""
        callback_executed = []

        def on_transition(ctx: AgentContext) -> None:
            callback_executed.append(True)

        transition = StateTransition(
            from_phase=AgentPhase.INITIALIZATION,
            to_phase=AgentPhase.INPUT_ANALYSIS,
            on_transition=on_transition,
        )

        room = Room(width=5.0, depth=4.0, height=2.8, room_type=RoomType.BEDROOM)
        context = AgentContext(room=room, room_type="bedroom")

        transition.execute(context)
        assert len(callback_executed) == 1


class TestPhaseConfig:
    """Tests for PhaseConfig."""

    def test_default_config(self) -> None:
        """Test default phase configuration."""
        config = PhaseConfig(phase=AgentPhase.INITIALIZATION)
        assert config.max_retries == 3
        assert config.timeout_seconds == 30.0
        assert config.required is True
        assert config.can_skip is False

    def test_custom_config(self) -> None:
        """Test custom phase configuration."""
        config = PhaseConfig(
            phase=AgentPhase.RULE_RETRIEVAL,
            max_retries=5,
            timeout_seconds=60.0,
            required=False,
            can_skip=True,
        )
        assert config.max_retries == 5
        assert config.can_skip is True


class TestPhaseResult:
    """Tests for PhaseResult."""

    def test_result_creation(self) -> None:
        """Test creating a phase result."""
        result = PhaseResult(
            phase=AgentPhase.INPUT_ANALYSIS,
            result=TransitionResult.SUCCESS,
            duration_ms=150.5,
        )
        assert result.is_success is True
        assert result.should_retry is False

    def test_failed_result(self) -> None:
        """Test failed phase result."""
        result = PhaseResult(
            phase=AgentPhase.PLACEMENT_EXECUTION,
            result=TransitionResult.FAILED,
            error="No space available",
        )
        assert result.is_success is False
        assert result.error == "No space available"

    def test_retry_result(self) -> None:
        """Test retry phase result."""
        result = PhaseResult(
            phase=AgentPhase.SCORING,
            result=TransitionResult.RETRY,
        )
        assert result.should_retry is True


class TestAgentStateMachine:
    """Tests for AgentStateMachine."""

    @pytest.fixture
    def state_machine(self) -> AgentStateMachine:
        """Create test state machine."""
        return AgentStateMachine()

    @pytest.fixture
    def context(self) -> AgentContext:
        """Create test agent context."""
        room = Room(width=5.0, depth=4.0, height=2.8, room_type=RoomType.BEDROOM)
        return AgentContext(room=room, room_type="bedroom")

    def test_initial_state(self, state_machine: AgentStateMachine) -> None:
        """Test initial state machine state."""
        assert len(state_machine._phase_history) == 0
        assert len(state_machine._retry_counts) == 0

    def test_can_transition_valid(
        self,
        state_machine: AgentStateMachine,
        context: AgentContext,
    ) -> None:
        """Test valid transition check."""
        context.phase = AgentPhase.INITIALIZATION
        assert state_machine.can_transition(context, AgentPhase.INPUT_ANALYSIS) is True

    def test_can_transition_invalid(
        self,
        state_machine: AgentStateMachine,
        context: AgentContext,
    ) -> None:
        """Test invalid transition check."""
        context.phase = AgentPhase.INITIALIZATION
        # Cannot jump directly to SCORING
        assert state_machine.can_transition(context, AgentPhase.SCORING) is False

    def test_transition_success(
        self,
        state_machine: AgentStateMachine,
        context: AgentContext,
    ) -> None:
        """Test successful transition."""
        context.phase = AgentPhase.INITIALIZATION
        result = state_machine.transition(context, AgentPhase.INPUT_ANALYSIS)

        assert result is True
        assert context.phase == AgentPhase.INPUT_ANALYSIS
        assert len(state_machine._phase_history) == 1

    def test_transition_failure(
        self,
        state_machine: AgentStateMachine,
        context: AgentContext,
    ) -> None:
        """Test failed transition."""
        context.phase = AgentPhase.INITIALIZATION
        result = state_machine.transition(context, AgentPhase.COMPLETED)

        assert result is False
        assert context.phase == AgentPhase.INITIALIZATION

    def test_get_next_phase(
        self,
        state_machine: AgentStateMachine,
        context: AgentContext,
    ) -> None:
        """Test getting next phase."""
        context.phase = AgentPhase.INITIALIZATION
        next_phase = state_machine.get_next_phase(context)
        assert next_phase == AgentPhase.INPUT_ANALYSIS

    def test_get_next_phase_terminal(
        self,
        state_machine: AgentStateMachine,
        context: AgentContext,
    ) -> None:
        """Test next phase from terminal state."""
        context.phase = AgentPhase.COMPLETED
        next_phase = state_machine.get_next_phase(context)
        assert next_phase is None

    def test_should_retry(
        self,
        state_machine: AgentStateMachine,
        context: AgentContext,
    ) -> None:
        """Test retry checking."""
        phase = AgentPhase.PLACEMENT_EXECUTION
        assert state_machine.should_retry(context, phase) is True

        # Record retries up to limit
        config = state_machine.get_phase_config(phase)
        for _ in range(config.max_retries):
            state_machine.record_retry(phase)

        assert state_machine.should_retry(context, phase) is False

    def test_reset_retries(
        self,
        state_machine: AgentStateMachine,
    ) -> None:
        """Test resetting retry counts."""
        phase = AgentPhase.SCORING
        state_machine.record_retry(phase)
        state_machine.record_retry(phase)

        assert state_machine._retry_counts[phase] == 2

        state_machine.reset_retries(phase)
        assert state_machine._retry_counts[phase] == 0

    def test_is_terminal(self, state_machine: AgentStateMachine) -> None:
        """Test terminal phase check."""
        assert state_machine.is_terminal(AgentPhase.COMPLETED) is True
        assert state_machine.is_terminal(AgentPhase.FAILED) is True
        assert state_machine.is_terminal(AgentPhase.SCORING) is False

    def test_reset(
        self,
        state_machine: AgentStateMachine,
        context: AgentContext,
    ) -> None:
        """Test state machine reset."""
        # Make some transitions
        context.phase = AgentPhase.INITIALIZATION
        state_machine.transition(context, AgentPhase.INPUT_ANALYSIS)
        state_machine.record_retry(AgentPhase.INPUT_ANALYSIS)

        state_machine.reset()

        assert len(state_machine._phase_history) == 0
        assert len(state_machine._retry_counts) == 0

    def test_add_custom_transition(
        self,
        state_machine: AgentStateMachine,
        context: AgentContext,
    ) -> None:
        """Test adding custom transition."""
        callback_called = []

        def callback(ctx: AgentContext) -> None:
            callback_called.append(True)

        transition = StateTransition(
            from_phase=AgentPhase.INITIALIZATION,
            to_phase=AgentPhase.INPUT_ANALYSIS,
            on_transition=callback,
        )
        state_machine.add_transition(transition)

        context.phase = AgentPhase.INITIALIZATION
        state_machine.transition(context, AgentPhase.INPUT_ANALYSIS)

        assert len(callback_called) == 1


class TestAgentStateMachineWorkflow:
    """Tests for full workflow execution."""

    @pytest.fixture
    def state_machine(self) -> AgentStateMachine:
        """Create test state machine."""
        return AgentStateMachine()

    @pytest.fixture
    def context(self) -> AgentContext:
        """Create test agent context."""
        room = Room(width=5.0, depth=4.0, height=2.8, room_type=RoomType.BEDROOM)
        return AgentContext(room=room, room_type="bedroom")

    def test_full_workflow(
        self,
        state_machine: AgentStateMachine,
        context: AgentContext,
    ) -> None:
        """Test running through full workflow."""
        workflow = create_standard_workflow()

        context.phase = workflow[0]

        # Transition through workflow
        for i in range(1, len(workflow)):
            target_phase = workflow[i]
            if state_machine.can_transition(context, target_phase):
                state_machine.transition(context, target_phase)

        assert context.phase == AgentPhase.COMPLETED

    def test_minimal_workflow(
        self,
        state_machine: AgentStateMachine,
        context: AgentContext,
    ) -> None:
        """Test minimal workflow."""
        workflow = create_minimal_workflow()

        context.phase = workflow[0]

        # Transition through workflow
        for i in range(1, len(workflow)):
            target_phase = workflow[i]
            if state_machine.can_transition(context, target_phase):
                state_machine.transition(context, target_phase)

        assert context.phase == AgentPhase.COMPLETED


class TestWorkflowState:
    """Tests for WorkflowState."""

    def test_state_creation(self) -> None:
        """Test creating workflow state."""
        state = WorkflowState()
        assert state.current_phase == AgentPhase.INITIALIZATION
        assert state.is_running is False
        assert state.is_completed is False
        assert state.is_failed is False

    def test_from_context(self) -> None:
        """Test creating state from context."""
        room = Room(width=5.0, depth=4.0, height=2.8, room_type=RoomType.BEDROOM)
        context = AgentContext(room=room, room_type="bedroom")
        context.phase = AgentPhase.COMPLETED

        state = WorkflowState.from_context(context)
        assert state.current_phase == AgentPhase.COMPLETED
        assert state.is_completed is True

    def test_to_dict(self) -> None:
        """Test converting state to dictionary."""
        state = WorkflowState(
            current_phase=AgentPhase.SCORING,
            is_running=True,
            phase_history=[AgentPhase.INITIALIZATION, AgentPhase.INPUT_ANALYSIS],
        )
        result = state.to_dict()

        assert result["current_phase"] == "scoring"
        assert result["is_running"] is True
        assert len(result["phase_history"]) == 2


class TestWorkflowFunctions:
    """Tests for workflow creation functions."""

    def test_create_standard_workflow(self) -> None:
        """Test creating standard workflow."""
        workflow = create_standard_workflow()
        assert workflow[0] == AgentPhase.INITIALIZATION
        assert workflow[-1] == AgentPhase.COMPLETED
        assert AgentPhase.RULE_RETRIEVAL in workflow

    def test_create_minimal_workflow(self) -> None:
        """Test creating minimal workflow."""
        workflow = create_minimal_workflow()
        assert workflow[0] == AgentPhase.INITIALIZATION
        assert workflow[-1] == AgentPhase.COMPLETED
        # Minimal workflow skips optional phases
        assert AgentPhase.RULE_RETRIEVAL not in workflow
        assert AgentPhase.COLLISION_RESOLUTION not in workflow


class TestPhaseConfigurations:
    """Tests for default phase configurations."""

    @pytest.fixture
    def state_machine(self) -> AgentStateMachine:
        """Create test state machine."""
        return AgentStateMachine()

    def test_all_phases_have_config(
        self,
        state_machine: AgentStateMachine,
    ) -> None:
        """Test that all workflow phases have configuration."""
        workflow = create_standard_workflow()

        for phase in workflow:
            if phase not in (AgentPhase.COMPLETED, AgentPhase.FAILED):
                config = state_machine.get_phase_config(phase)
                assert config is not None, f"Missing config for {phase}"

    def test_set_custom_config(
        self,
        state_machine: AgentStateMachine,
    ) -> None:
        """Test setting custom phase configuration."""
        custom_config = PhaseConfig(
            phase=AgentPhase.PLACEMENT_EXECUTION,
            max_retries=10,
            timeout_seconds=120.0,
        )
        state_machine.set_phase_config(custom_config)

        retrieved = state_machine.get_phase_config(AgentPhase.PLACEMENT_EXECUTION)
        assert retrieved.max_retries == 10
        assert retrieved.timeout_seconds == 120.0
