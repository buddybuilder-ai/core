"""Application services for feng shui layout generation."""

from src.modules.layout.application.services.collision_checker import (
    Collision,
    check_collisions,
)
from src.modules.layout.application.services.context_injector import (
    ContextInjector,
    RagContext,
)
from src.modules.layout.application.services.feng_shui_checker import (
    FengShuiViolation,
    check_feng_shui,
)
from src.modules.layout.application.services.feng_shui_scorer import (
    FengShuiElement,
    FengShuiScorer,
    ScoringConfig,
    ScoringResult,
)
from src.modules.layout.application.services.furniture_selector import (
    FurnitureSelection,
    FurnitureSelectionResult,
    FurnitureSelector,
)
from src.modules.layout.application.services.input_analyzer import (
    InputAnalysisResult,
    InputAnalyzer,
    ValidationIssue,
    ValidationSeverity,
)
from src.modules.layout.application.services.layout_resolver import (
    LayoutResolutionResult,
    LayoutResolver,
    SemanticPlacementSchema,
)
from src.modules.layout.application.services.output_builder import (
    LayoutReport,
    OutputBuilder,
    OutputConfig,
    OutputSummary,
    build_layout_report,
)
from src.modules.layout.application.services.placement_engine import (
    FallbackStrategy,
    PlacementConfig,
    PlacementEngine,
    RotationStrategy,
)
from src.modules.layout.application.services.rag_service import FengShuiRAGService
from src.modules.layout.application.services.spatial_analyzer import SpatialAnalyzer
from src.modules.layout.application.services.spatial_resolver import (
    FurnitureSize,
    PhysicalPlacement,
    RoomSpec,
    SemanticPlacement,
    SpatialResolver,
)

__all__ = [
    "FallbackStrategy",
    "FengShuiElement",
    "FengShuiScorer",
    "FurnitureSelection",
    "FurnitureSelectionResult",
    "FurnitureSelector",
    "InputAnalyzer",
    "InputAnalysisResult",
    "LayoutReport",
    "OutputBuilder",
    "OutputConfig",
    "OutputSummary",
    "PlacementConfig",
    "PlacementEngine",
    "RotationStrategy",
    "ScoringConfig",
    "ScoringResult",
    "SpatialAnalyzer",
    "ValidationIssue",
    "ValidationSeverity",
    "build_layout_report",
    # Spatial engine
    "Collision",
    "FengShuiViolation",
    "FurnitureSize",
    "PhysicalPlacement",
    "RoomSpec",
    "SemanticPlacement",
    "SpatialResolver",
    "check_collisions",
    "check_feng_shui",
    # Integration layer
    "LayoutResolutionResult",
    "LayoutResolver",
    "SemanticPlacementSchema",
    # RAG context injection
    "ContextInjector",
    "RagContext",
    # Feng Shui RAG Service (ConversationRAGChain port)
    "FengShuiRAGService",
]
