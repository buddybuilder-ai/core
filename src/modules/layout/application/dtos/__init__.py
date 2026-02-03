"""DTOs for feng shui layout application layer."""

from src.modules.layout.application.dtos.agent_context import (
    AgentContext,
    AgentPhase,
    AgentState,
    PlacedFurniture,
    PlacementStrategy,
    UserPreferences,
)
from src.modules.layout.application.dtos.placement_result import (
    BatchPlacementResult,
    FallbackAction,
    LayoutOutput,
    PlacementAttempt,
    PlacementFailureReason,
    PlacementResult,
    PlacementStatus,
)
from src.modules.layout.application.dtos.spatial_analysis import (
    AnalysisZone,
    CommandPosition,
    FengShuiDirection,
    SpatialAnalysisResult,
    TrafficFlowAnalysis,
    ZoneQuality,
)

__all__ = [
    # Agent Context
    "AgentContext",
    "AgentPhase",
    "AgentState",
    "PlacedFurniture",
    "PlacementStrategy",
    "UserPreferences",
    # Placement Result
    "BatchPlacementResult",
    "FallbackAction",
    "LayoutOutput",
    "PlacementAttempt",
    "PlacementFailureReason",
    "PlacementResult",
    "PlacementStatus",
    # Spatial Analysis
    "AnalysisZone",
    "CommandPosition",
    "FengShuiDirection",
    "SpatialAnalysisResult",
    "TrafficFlowAnalysis",
    "ZoneQuality",
]
