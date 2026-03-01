"""Agent module for feng shui layout generation.

Note: LayoutOrchestrator and the state machine are superseded by
PipelineOrchestrator (src/modules/layout/application/pipeline/).
They remain here for reference and will be removed in a future release.
"""

from src.modules.layout.application.agent.orchestrator import (
    LayoutOrchestrator,
    LayoutRequest,
    LayoutResponse,
    OrchestratorConfig,
    generate_layout,
)
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

__all__ = [
    "AgentStateMachine",
    "LayoutOrchestrator",
    "LayoutRequest",
    "LayoutResponse",
    "OrchestratorConfig",
    "PhaseConfig",
    "PhaseResult",
    "StateTransition",
    "TransitionResult",
    "WorkflowState",
    "create_minimal_workflow",
    "create_standard_workflow",
    "generate_layout",
]
