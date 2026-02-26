"""5-Step Agentic Layout Pipeline.

Pipeline Steps:
    1. Structured Data Builder — Parse user input to structured RoomSpec
    2. Layout Generator (Planner) — Heuristic placement (big item, wall align)
    3. Rule Checker (Dual-rule) — Universal Standards + Feng Shui
    4. Repair (Auto-fix) — Local search fix (shift/rotate/swap)
    5. Explainer — Summarize & explain fixes
"""

from src.modules.layout.application.pipeline.models import (
    Conflict,
    ConflictSeverity,
    ConflictType,
    PipelineConfig,
    PipelineResult,
    PipelineState,
    PipelineStep,
    RepairAction,
    RepairActionType,
    SSEEvent,
    SSEEventType,
    StepResult,
    StepStatus,
)
from src.modules.layout.application.pipeline.orchestrator import PipelineOrchestrator
from src.modules.layout.application.pipeline.steps import (
    ExplainerStep,
    LayoutGeneratorStep,
    RepairStep,
    RuleCheckerStep,
    StructuredDataBuilderStep,
)

__all__ = [
    "Conflict",
    "ConflictSeverity",
    "ConflictType",
    "ExplainerStep",
    "LayoutGeneratorStep",
    "PipelineConfig",
    "PipelineOrchestrator",
    "PipelineResult",
    "PipelineState",
    "PipelineStep",
    "RepairAction",
    "RepairActionType",
    "RepairStep",
    "RuleCheckerStep",
    "SSEEvent",
    "SSEEventType",
    "StepResult",
    "StepStatus",
    "StructuredDataBuilderStep",
]
