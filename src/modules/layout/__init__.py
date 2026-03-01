"""Feng Shui Layout Module.

This module provides AI-powered furniture layout generation using feng shui principles.
It includes domain entities, application services, infrastructure tools, and an
orchestrator for coordinating the complete layout generation workflow.

Quick Start:
    >>> from src.modules.layout import generate_layout, LayoutRequest, LayoutOrchestrator
    >>> response = await generate_layout("bedroom", width=5.0, depth=4.0)
    >>> print(f"Score: {response.feng_shui_score}, Furniture: {response.furniture_count}")

Public API:
    - LayoutOrchestrator: Main orchestrator for layout generation
    - LayoutRequest: Request dataclass for layout generation
    - LayoutResponse: Response dataclass with layout results
    - OrchestratorConfig: Configuration for the orchestrator
    - generate_layout: Convenience function for simple layout generation
"""

# Core orchestration (primary public API)
# DTOs for working with the agent
from src.modules.layout.application import (
    AgentContext,
    AgentPhase,
    BatchPlacementResult,
    LayoutOutput,
    PlacedFurniture,
    PlacementStrategy,
    SpatialAnalysisResult,
    UserPreferences,
)
from src.modules.layout.application.agent import (
    LayoutOrchestrator,
    LayoutRequest,
    LayoutResponse,
    OrchestratorConfig,
    generate_layout,
)

# Services for direct use
from src.modules.layout.application.services import (
    FengShuiScorer,
    FurnitureSelector,
    InputAnalyzer,
    OutputBuilder,
    PlacementEngine,
    SpatialAnalyzer,
)

# Domain entities
from src.modules.layout.domain import (
    DoorPosition,
    FengShuiScore,
    Furniture,
    FurnitureCategory,
    Placement,
    Position3D,
    Room,
    RoomType,
    WallSide,
    WindowPosition,
)

__all__ = [
    # Primary API - Orchestration
    "LayoutOrchestrator",
    "LayoutRequest",
    "LayoutResponse",
    "OrchestratorConfig",
    "generate_layout",
    # Domain Entities
    "DoorPosition",
    "FengShuiScore",
    "Furniture",
    "FurnitureCategory",
    "Placement",
    "Position3D",
    "Room",
    "RoomType",
    "WallSide",
    "WindowPosition",
    # DTOs
    "AgentContext",
    "AgentPhase",
    "BatchPlacementResult",
    "LayoutOutput",
    "PlacedFurniture",
    "PlacementStrategy",
    "SpatialAnalysisResult",
    "UserPreferences",
    # Services
    "FengShuiScorer",
    "FurnitureSelector",
    "InputAnalyzer",
    "OutputBuilder",
    "PlacementEngine",
    "SpatialAnalyzer",
]
