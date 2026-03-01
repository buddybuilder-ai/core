"""Pipeline domain models for the 5-step agentic layout pipeline."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class PipelineStep(str, Enum):
    """The 5 steps of the agentic layout pipeline."""

    STRUCTURED_DATA_BUILDER = "structured_data_builder"
    LAYOUT_GENERATOR = "layout_generator"
    RULE_CHECKER = "rule_checker"
    REPAIR = "repair"
    EXPLAINER = "explainer"


class StepStatus(str, Enum):
    """Status of a pipeline step."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class ConflictType(str, Enum):
    """Types of layout conflicts detected by Rule Checker."""

    OVERLAP = "overlap"
    CLEARANCE_VIOLATION = "clearance_violation"
    DOOR_BLOCKED = "door_blocked"
    WINDOW_BLOCKED = "window_blocked"
    WALKWAY_TOO_NARROW = "walkway_too_narrow"
    OUT_OF_BOUNDS = "out_of_bounds"
    # Feng Shui
    BAD_COMMAND_POSITION = "bad_command_position"
    ELEMENT_IMBALANCE = "element_imbalance"
    SHA_CHI_ALIGNMENT = "sha_chi_alignment"
    BACK_TO_DOOR = "back_to_door"
    BLOCKED_CHI_FLOW = "blocked_chi_flow"


class ConflictSeverity(str, Enum):
    """Severity levels for conflicts."""

    CRITICAL = "critical"  # Must fix (e.g. door blocked)
    WARNING = "warning"  # Should fix (e.g. clearance violation)
    INFO = "info"  # Nice to fix (e.g. feng shui suggestion)


class RepairActionType(str, Enum):
    """Types of repair actions."""

    SHIFT = "shift"
    ROTATE = "rotate"
    SWAP = "swap"
    REMOVE = "remove"


class SSEEventType(str, Enum):
    """SSE event types streamed to frontend."""

    PIPELINE_STARTED = "pipeline_started"
    STEP_STARTED = "step_started"
    STEP_PROGRESS = "step_progress"
    STEP_COMPLETED = "step_completed"
    STEP_FAILED = "step_failed"
    CONFLICT_FOUND = "conflict_found"
    REPAIR_APPLIED = "repair_applied"
    LAYOUT_UPDATED = "layout_updated"
    PIPELINE_COMPLETED = "pipeline_completed"
    PIPELINE_FAILED = "pipeline_failed"
    # Router + Modifier events
    ROUTER_CLASSIFIED = "router_classified"
    MODIFIER_STARTED = "modifier_started"
    MODIFIER_UPDATED = "modifier_updated"
    MODIFIER_COMPLETED = "modifier_completed"
    # Personality mode
    MODE_CHANGED = "mode_changed"


@dataclass
class Conflict:
    """A layout conflict detected by the Rule Checker."""

    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    conflict_type: ConflictType = ConflictType.OVERLAP
    severity: ConflictSeverity = ConflictSeverity.WARNING
    description: str = ""
    items_involved: list[str] = field(default_factory=list)
    suggestion: str = ""
    resolved: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.conflict_type.value,
            "severity": self.severity.value,
            "description": self.description,
            "items_involved": self.items_involved,
            "suggestion": self.suggestion,
            "resolved": self.resolved,
        }


@dataclass
class RepairAction:
    """A repair action applied to fix a conflict."""

    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    action_type: RepairActionType = RepairActionType.SHIFT
    conflict_id: str = ""
    furniture_id: str = ""
    description: str = ""
    before: dict[str, Any] = field(default_factory=dict)
    after: dict[str, Any] = field(default_factory=dict)
    success: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "action_type": self.action_type.value,
            "conflict_id": self.conflict_id,
            "furniture_id": self.furniture_id,
            "description": self.description,
            "before": self.before,
            "after": self.after,
            "success": self.success,
        }


@dataclass
class StepResult:
    """Result from executing a single pipeline step."""

    step: PipelineStep
    status: StepStatus = StepStatus.PENDING
    duration_ms: float = 0.0
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "step": self.step.value,
            "status": self.status.value,
            "duration_ms": round(self.duration_ms, 1),
            "data": self.data,
            "error": self.error,
        }


@dataclass
class PipelineConfig:
    """Configuration for the pipeline."""

    max_repair_loops: int = 3
    llm_model: str = "anthropic/claude-3.5-sonnet"
    llm_temperature: float = 0.3
    step_timeout_seconds: float = 60.0
    total_timeout_seconds: float = 300.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_repair_loops": self.max_repair_loops,
            "llm_model": self.llm_model,
            "llm_temperature": self.llm_temperature,
            "step_timeout_seconds": self.step_timeout_seconds,
            "total_timeout_seconds": self.total_timeout_seconds,
        }


@dataclass
class PipelineState:
    """Mutable state maintained throughout the pipeline."""

    # Pipeline tracking
    pipeline_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    current_step: PipelineStep | None = None
    repair_iteration: int = 0
    step_results: list[StepResult] = field(default_factory=list)
    started_at: float = field(default_factory=time.time)

    # Data flowing through pipeline
    room_spec: dict[str, Any] = field(default_factory=dict)
    layout_items: list[dict[str, Any]] = field(default_factory=list)
    conflicts: list[Conflict] = field(default_factory=list)
    repair_actions: list[RepairAction] = field(default_factory=list)
    explanation: str = ""

    # Feng Shui
    feng_shui_score: dict[str, Any] = field(default_factory=dict)

    # RAG context retrieved between Step 1 and Step 2
    rag_context: dict[str, Any] = field(default_factory=dict)

    # Personality mode for Explainer (Step 5)
    personality_mode: str = "buddy"

    @property
    def unresolved_conflicts(self) -> list[Conflict]:
        return [c for c in self.conflicts if not c.resolved]

    @property
    def critical_conflicts(self) -> list[Conflict]:
        return [
            c for c in self.unresolved_conflicts
            if c.severity == ConflictSeverity.CRITICAL
        ]

    @property
    def elapsed_ms(self) -> float:
        return (time.time() - self.started_at) * 1000

    def to_dict(self) -> dict[str, Any]:
        return {
            "pipeline_id": self.pipeline_id,
            "current_step": self.current_step.value if self.current_step else None,
            "repair_iteration": self.repair_iteration,
            "step_results": [r.to_dict() for r in self.step_results],
            "layout_items_count": len(self.layout_items),
            "conflicts_count": len(self.conflicts),
            "unresolved_count": len(self.unresolved_conflicts),
            "repair_actions_count": len(self.repair_actions),
            "feng_shui_score": self.feng_shui_score,
            "elapsed_ms": round(self.elapsed_ms, 1),
        }


@dataclass
class PipelineResult:
    """Final result of the entire pipeline."""

    success: bool = False
    pipeline_id: str = ""
    layout_items: list[dict[str, Any]] = field(default_factory=list)
    feng_shui_score: dict[str, Any] = field(default_factory=dict)
    conflicts: list[Conflict] = field(default_factory=list)
    repair_actions: list[RepairAction] = field(default_factory=list)
    explanation: str = ""
    step_results: list[StepResult] = field(default_factory=list)
    total_duration_ms: float = 0.0
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "pipeline_id": self.pipeline_id,
            "layout_items": self.layout_items,
            "feng_shui_score": self.feng_shui_score,
            "conflicts": [c.to_dict() for c in self.conflicts],
            "repair_actions": [r.to_dict() for r in self.repair_actions],
            "explanation": self.explanation,
            "step_results": [r.to_dict() for r in self.step_results],
            "total_duration_ms": round(self.total_duration_ms, 1),
            "error": self.error,
        }


@dataclass
class SSEEvent:
    """An event to be streamed via SSE."""

    event_type: SSEEventType
    data: dict[str, Any] = field(default_factory=dict)

    def to_sse(self) -> str:
        """Format as SSE string."""
        import json
        payload = json.dumps({"type": self.event_type.value, **self.data})
        return f"event: {self.event_type.value}\ndata: {payload}\n\n"
