"""Agent orchestrator for feng shui layout generation."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from src.modules.layout.application.agent.state_machine import (
    AgentStateMachine,
    PhaseResult,
    TransitionResult,
    WorkflowState,
    create_minimal_workflow,
    create_standard_workflow,
)
from src.modules.layout.application.dtos import (
    AgentContext,
    AgentPhase,
    UserPreferences,
)
from src.modules.layout.application.dtos.placement_result import (
    BatchPlacementResult,
    LayoutOutput,
)
from src.modules.layout.application.services import (
    FengShuiScorer,
    FurnitureSelection,
    FurnitureSelector,
    InputAnalyzer,
    OutputBuilder,
    PlacementEngine,
    SpatialAnalyzer,
)
from src.modules.layout.domain.entities import Room, RoomType
from src.modules.layout.domain.value_objects import FengShuiScore
from src.modules.layout.infrastructure.tools import InMemoryFurnitureDbTool

logger = logging.getLogger(__name__)


@dataclass
class OrchestratorConfig:
    """Configuration for the agent orchestrator.

    Attributes:
        use_minimal_workflow: Use minimal workflow (skip optional phases).
        use_llm: Use LLM for intelligent layout decisions.
        max_retries: Maximum retries for failed phases.
        timeout_seconds: Overall timeout for layout generation.
        min_acceptable_score: Minimum acceptable feng shui score.
        auto_retry_low_score: Automatically retry if score is too low.
    """

    use_minimal_workflow: bool = False
    use_llm: bool = False
    max_retries: int = 3
    timeout_seconds: float = 120.0
    min_acceptable_score: int = 40
    auto_retry_low_score: bool = True


@dataclass
class LayoutRequest:
    """Request for layout generation.

    Attributes:
        room_type: Type of room (bedroom, living_room, office, dining_room).
        width: Room width in meters.
        depth: Room depth in meters.
        height: Room height in meters (default 2.8).
        budget_level: Budget level (low, medium, high).
        style_preference: Style preference.
        max_furniture_items: Maximum furniture items.
        doors: Door specifications.
        windows: Window specifications.
        custom_preferences: Additional preferences.
    """

    room_type: str
    width: float
    depth: float
    height: float = 2.8
    budget_level: str = "medium"
    style_preference: str = "modern"
    max_furniture_items: int = 10
    doors: list[dict[str, Any]] = field(default_factory=list)
    windows: list[dict[str, Any]] = field(default_factory=list)
    custom_preferences: dict[str, Any] = field(default_factory=dict)

    def to_input_data(self) -> dict[str, Any]:
        """Convert to input data dictionary."""
        return {
            "room_type": self.room_type,
            "dimensions": {
                "width": self.width,
                "depth": self.depth,
                "height": self.height,
            },
            "doors": self.doors,
            "windows": self.windows,
            "preferences": {
                "budget_level": self.budget_level,
                "style_preference": self.style_preference,
                "max_items": self.max_furniture_items,
                **self.custom_preferences,
            },
        }


@dataclass
class LayoutResponse:
    """Response from layout generation.

    Attributes:
        success: Whether generation succeeded.
        output: The generated layout output.
        feng_shui_score: Final feng shui score.
        furniture_count: Number of furniture items placed.
        execution_time_ms: Total execution time.
        phase_results: Results from each phase.
        error_message: Error message if failed.
    """

    success: bool
    output: LayoutOutput | None = None
    feng_shui_score: int = 0
    furniture_count: int = 0
    execution_time_ms: float = 0.0
    phase_results: list[PhaseResult] = field(default_factory=list)
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "feng_shui_score": self.feng_shui_score,
            "furniture_count": self.furniture_count,
            "execution_time_ms": self.execution_time_ms,
            "error_message": self.error_message,
            "output": self.output.to_dict() if self.output else None,
        }


class LayoutOrchestrator:
    """Orchestrator for feng shui layout generation.

    This class coordinates all services and tools to generate
    a complete feng shui-optimized room layout. Supports both
    deterministic (rule-based) and LLM-powered modes.
    """

    def __init__(self, config: OrchestratorConfig | None = None) -> None:
        """Initialize the orchestrator.

        Args:
            config: Orchestrator configuration.
        """
        self.config = config or OrchestratorConfig()

        # Initialize services
        self._input_analyzer = InputAnalyzer()
        self._spatial_analyzer = SpatialAnalyzer()
        self._furniture_tool = InMemoryFurnitureDbTool()
        self._furniture_selector = FurnitureSelector(self._furniture_tool)
        self._scorer = FengShuiScorer()
        self._output_builder = OutputBuilder()

        # Initialize state machine
        self._state_machine = AgentStateMachine()

        # Initialize LLM agent if enabled
        self._llm_agent = None
        if self.config.use_llm:
            try:
                from src.modules.layout.infrastructure.llm import (
                    FengShuiLLMAgent,
                    LLMConfig,
                )

                self._llm_agent = FengShuiLLMAgent(LLMConfig())
                logger.info("LLM agent initialized successfully")
            except Exception as e:
                logger.warning(f"Failed to initialize LLM agent: {e}")
                logger.info("Falling back to deterministic mode")

        # Current context and state
        self._context: AgentContext | None = None
        self._selections: list[FurnitureSelection] = []
        self._placement_result: BatchPlacementResult | None = None
        self._request: LayoutRequest | None = None

    async def generate_layout(self, request: LayoutRequest) -> LayoutResponse:
        """Generate a feng shui layout.

        Args:
            request: Layout request.

        Returns:
            LayoutResponse with generated layout.
        """
        start_time = time.time()
        phase_results: list[PhaseResult] = []
        self._request = request  # Store for LLM phases

        try:
            # Get workflow
            workflow = (
                create_minimal_workflow()
                if self.config.use_minimal_workflow
                else create_standard_workflow()
            )

            # Execute each phase
            for phase in workflow:
                if self._state_machine.is_terminal(phase):
                    break

                result = await self._execute_phase(phase, request)
                phase_results.append(result)

                if not result.is_success:
                    # Check if we should retry
                    if (
                        result.should_retry
                        and self._context is not None
                        and self._state_machine.should_retry(self._context, phase)
                    ):
                        self._state_machine.record_retry(phase)
                        continue

                    # Phase failed
                    return LayoutResponse(
                        success=False,
                        phase_results=phase_results,
                        error_message=result.error or f"Phase {phase.value} failed",
                        execution_time_ms=(time.time() - start_time) * 1000,
                    )

            # Build final output
            assert self._context is not None
            output = self._output_builder.build_from_context(self._context)

            return LayoutResponse(
                success=True,
                output=output,
                feng_shui_score=(
                    self._context.feng_shui_score.total if self._context.feng_shui_score else 0
                ),
                furniture_count=len(self._context.placed_furniture),
                phase_results=phase_results,
                execution_time_ms=(time.time() - start_time) * 1000,
            )

        except Exception as e:
            return LayoutResponse(
                success=False,
                phase_results=phase_results,
                error_message=str(e),
                execution_time_ms=(time.time() - start_time) * 1000,
            )

    async def _execute_phase(
        self,
        phase: AgentPhase,
        request: LayoutRequest,
    ) -> PhaseResult:
        """Execute a single phase.

        Args:
            phase: Phase to execute.
            request: Original layout request.

        Returns:
            PhaseResult with execution result.
        """
        start_time = time.time()

        try:
            if phase == AgentPhase.INITIALIZATION:
                return await self._phase_initialization(request)

            elif phase == AgentPhase.INPUT_ANALYSIS:
                return await self._phase_input_analysis(request)

            elif phase == AgentPhase.SPATIAL_ANALYSIS:
                return await self._phase_spatial_analysis()

            elif phase == AgentPhase.RULE_RETRIEVAL:
                return await self._phase_rule_retrieval()

            elif phase == AgentPhase.FURNITURE_SELECTION:
                return await self._phase_furniture_selection(request)

            elif phase == AgentPhase.PLACEMENT_PLANNING:
                return await self._phase_placement_planning()

            elif phase == AgentPhase.PLACEMENT_EXECUTION:
                return await self._phase_placement_execution()

            elif phase == AgentPhase.COLLISION_RESOLUTION:
                return await self._phase_collision_resolution()

            elif phase == AgentPhase.SCORING:
                return await self._phase_scoring()

            elif phase == AgentPhase.VALIDATION:
                return await self._phase_validation()

            elif phase == AgentPhase.OUTPUT_GENERATION:
                return await self._phase_output_generation()

            else:
                return PhaseResult(
                    phase=phase,
                    result=TransitionResult.SUCCESS,
                    duration_ms=(time.time() - start_time) * 1000,
                )

        except Exception as e:
            return PhaseResult(
                phase=phase,
                result=TransitionResult.FAILED,
                error=str(e),
                duration_ms=(time.time() - start_time) * 1000,
            )

    async def _phase_initialization(self, request: LayoutRequest) -> PhaseResult:
        """Initialize the layout generation."""
        # Map room type
        room_type_map = {
            "bedroom": RoomType.BEDROOM,
            "living_room": RoomType.LIVING_ROOM,
            "office": RoomType.OFFICE,
            "dining_room": RoomType.DINING_ROOM,
        }
        room_type_enum = room_type_map.get(request.room_type, RoomType.BEDROOM)

        # Create room
        room = Room(
            width=request.width,
            depth=request.depth,
            height=request.height,
            room_type=room_type_enum,
        )

        # Create context
        self._context = AgentContext(
            room=room,
            room_type=request.room_type,
            user_preferences=UserPreferences(
                budget_level=request.budget_level,
                style_preference=request.style_preference,
                custom_preferences=request.custom_preferences,
            ),
        )

        self._context.advance_phase(AgentPhase.INITIALIZATION)

        return PhaseResult(
            phase=AgentPhase.INITIALIZATION,
            result=TransitionResult.SUCCESS,
            data={"room_type": request.room_type},
        )

    async def _phase_input_analysis(self, request: LayoutRequest) -> PhaseResult:
        """Analyze input data."""
        assert self._context is not None
        input_data = request.to_input_data()
        analysis = self._input_analyzer.analyze(input_data)

        if analysis.has_errors:
            return PhaseResult(
                phase=AgentPhase.INPUT_ANALYSIS,
                result=TransitionResult.FAILED,
                error="; ".join(analysis.error_messages),
            )

        self._context.advance_phase(AgentPhase.INPUT_ANALYSIS)

        return PhaseResult(
            phase=AgentPhase.INPUT_ANALYSIS,
            result=TransitionResult.SUCCESS,
            data={"warnings": analysis.warning_messages},
        )

    async def _phase_spatial_analysis(self) -> PhaseResult:
        """Analyze room spatial characteristics."""
        assert self._context is not None
        analysis = self._spatial_analyzer.analyze(self._context.room)

        # Store in context metadata
        self._context.metadata["spatial_analysis"] = analysis.to_dict()
        self._context.metadata["usable_area"] = analysis.usable_area
        self._context.metadata["command_positions"] = [
            p.to_dict() for p in analysis.command_positions
        ]

        self._context.advance_phase(AgentPhase.SPATIAL_ANALYSIS)

        return PhaseResult(
            phase=AgentPhase.SPATIAL_ANALYSIS,
            result=TransitionResult.SUCCESS,
            data={
                "usable_area": analysis.usable_area,
                "command_position_count": len(analysis.command_positions),
            },
        )

    async def _phase_rule_retrieval(self) -> PhaseResult:
        """Retrieve feng shui rules (optional phase)."""
        assert self._context is not None
        # This phase can be skipped - rules are embedded in services
        self._context.advance_phase(AgentPhase.RULE_RETRIEVAL)

        return PhaseResult(
            phase=AgentPhase.RULE_RETRIEVAL,
            result=TransitionResult.SUCCESS,
            data={"rules_loaded": True},
        )

    async def _phase_furniture_selection(
        self,
        request: LayoutRequest,
    ) -> PhaseResult:
        """Select furniture for the room."""
        assert self._context is not None
        usable_area = self._context.metadata.get(
            "usable_area",
            request.width * request.depth * 0.8,
        )

        result = await self._furniture_selector.select_furniture(
            room_type=request.room_type,
            usable_area=usable_area,
            preferences=self._context.user_preferences,
            max_items=request.max_furniture_items,
        )

        self._selections = result.get_by_priority()
        self._furniture_selector.update_context(self._context, result)

        if not self._selections:
            return PhaseResult(
                phase=AgentPhase.FURNITURE_SELECTION,
                result=TransitionResult.FAILED,
                error="No furniture could be selected",
            )

        self._context.advance_phase(AgentPhase.FURNITURE_SELECTION)

        return PhaseResult(
            phase=AgentPhase.FURNITURE_SELECTION,
            result=TransitionResult.SUCCESS,
            data={
                "selected_count": len(self._selections),
                "essential_count": result.essential_count,
            },
        )

    async def _phase_placement_planning(self) -> PhaseResult:
        """Plan furniture placement."""
        assert self._context is not None
        # Planning is integrated into execution
        self._context.advance_phase(AgentPhase.PLACEMENT_PLANNING)

        return PhaseResult(
            phase=AgentPhase.PLACEMENT_PLANNING,
            result=TransitionResult.SUCCESS,
        )

    async def _phase_placement_execution(self) -> PhaseResult:
        """Execute furniture placement."""
        assert self._context is not None
        engine = PlacementEngine(
            room_width=self._context.room.width,
            room_depth=self._context.room.depth,
        )

        # Get spatial analysis if available
        spatial_analysis = None
        if "spatial_analysis" in self._context.metadata:
            # Note: Would need proper deserialization in production
            pass

        self._placement_result = engine.place_all(self._selections, spatial_analysis)
        engine.update_context(self._context, self._placement_result)

        if self._placement_result.placed_count == 0:
            return PhaseResult(
                phase=AgentPhase.PLACEMENT_EXECUTION,
                result=TransitionResult.FAILED,
                error="No furniture could be placed",
            )

        self._context.advance_phase(AgentPhase.PLACEMENT_EXECUTION)

        return PhaseResult(
            phase=AgentPhase.PLACEMENT_EXECUTION,
            result=TransitionResult.SUCCESS,
            data={
                "placed_count": self._placement_result.placed_count,
                "success_rate": self._placement_result.success_rate,
            },
        )

    async def _phase_collision_resolution(self) -> PhaseResult:
        """Resolve any placement collisions (optional phase)."""
        assert self._context is not None
        # Collision resolution is handled during placement
        self._context.advance_phase(AgentPhase.COLLISION_RESOLUTION)

        return PhaseResult(
            phase=AgentPhase.COLLISION_RESOLUTION,
            result=TransitionResult.SUCCESS,
        )

    async def _phase_scoring(self) -> PhaseResult:
        """Score the layout using rule-based scorer or LLM."""
        assert self._context is not None
        # Try LLM scoring if enabled
        if self._llm_agent and self._request:
            llm_result = await self._phase_scoring_with_llm()
            if llm_result:
                return llm_result

        # Fallback to deterministic scoring
        result = self._scorer.score_layout(
            room=self._context.room,
            placed_furniture=self._context.placed_furniture,
        )
        self._scorer.update_context(self._context, result)

        # Check if score is acceptable
        if (
            self.config.auto_retry_low_score
            and result.score.total < self.config.min_acceptable_score
        ):
            return PhaseResult(
                phase=AgentPhase.SCORING,
                result=TransitionResult.RETRY,
                error=f"Score too low: {result.score.total}",
                data={"score": result.score.total},
            )

        self._context.advance_phase(AgentPhase.SCORING)

        return PhaseResult(
            phase=AgentPhase.SCORING,
            result=TransitionResult.SUCCESS,
            data={
                "total_score": result.score.total,
                "grade": result.score.grade,
                "llm_used": False,
            },
        )

    async def _phase_scoring_with_llm(self) -> PhaseResult | None:
        """Score layout using LLM for intelligent analysis."""
        assert self._context is not None
        assert self._llm_agent is not None
        assert self._request is not None
        try:
            # Prepare furniture placements for LLM
            placements = [
                {
                    "id": f.id,
                    "name": f.name,
                    "category": f.category,
                    "pos_x": f.pos_x,
                    "pos_z": f.pos_z,
                    "width": f.width,
                    "depth": f.depth,
                    "rotation": f.rotation,
                }
                for f in self._context.placed_furniture
            ]

            logger.info("Invoking LLM for layout scoring...")
            llm_response = await self._llm_agent.score_layout(
                room_type=self._request.room_type,
                width=self._request.width,
                depth=self._request.depth,
                furniture_placements=placements,
            )

            if not llm_response.success:
                logger.warning(f"LLM scoring failed: {llm_response.error}")
                return None

            # Extract scores from LLM response
            content = llm_response.content
            scores = content.get("scores", {})

            score = FengShuiScore(
                command_position=min(30, max(0, scores.get("command_position", 15))),
                five_elements=min(20, max(0, scores.get("five_elements", 10))),
                chi_flow=min(25, max(0, scores.get("chi_flow", 12))),
                sha_chi_avoidance=min(25, max(0, scores.get("sha_chi_avoidance", 12))),
            )

            # Update context with LLM score
            self._context.feng_shui_score = score

            # Add LLM recommendations to context
            recommendations = content.get("recommendations", [])
            for rec in recommendations[:3]:
                self._context.add_warning(rec)

            # Store LLM analysis in metadata
            self._context.metadata["llm_analysis"] = {
                "component_analysis": content.get("component_analysis", {}),
                "grade": content.get("grade", score.grade),
                "tokens_used": llm_response.tokens_used,
            }

            logger.info(f"LLM scoring complete: {score.total}/100 ({score.grade})")

            # Check if score is acceptable
            if self.config.auto_retry_low_score and score.total < self.config.min_acceptable_score:
                return PhaseResult(
                    phase=AgentPhase.SCORING,
                    result=TransitionResult.RETRY,
                    error=f"LLM Score too low: {score.total}",
                    data={"score": score.total, "llm_used": True},
                )

            self._context.advance_phase(AgentPhase.SCORING)

            return PhaseResult(
                phase=AgentPhase.SCORING,
                result=TransitionResult.SUCCESS,
                data={
                    "total_score": score.total,
                    "grade": score.grade,
                    "llm_used": True,
                    "tokens_used": llm_response.tokens_used,
                },
            )

        except Exception as e:
            logger.error(f"LLM scoring error: {e}")
            return None

    async def _phase_validation(self) -> PhaseResult:
        """Validate the layout."""
        assert self._context is not None
        # Check for errors in context
        if self._context.validation_errors:
            return PhaseResult(
                phase=AgentPhase.VALIDATION,
                result=TransitionResult.FAILED,
                error="; ".join(self._context.validation_errors),
            )

        # Check essential furniture placed
        if not self._context.essential_furniture_placed:
            self._context.add_warning("Not all essential furniture placed")

        self._context.advance_phase(AgentPhase.VALIDATION)

        return PhaseResult(
            phase=AgentPhase.VALIDATION,
            result=TransitionResult.SUCCESS,
            data={"warning_count": len(self._context.validation_warnings)},
        )

    async def _phase_output_generation(self) -> PhaseResult:
        """Generate final output."""
        assert self._context is not None
        self._context.advance_phase(AgentPhase.OUTPUT_GENERATION)

        return PhaseResult(
            phase=AgentPhase.OUTPUT_GENERATION,
            result=TransitionResult.SUCCESS,
        )

    def get_workflow_state(self) -> WorkflowState:
        """Get current workflow state."""
        if self._context:
            return WorkflowState.from_context(self._context)
        return WorkflowState()


async def generate_layout(
    room_type: str,
    width: float,
    depth: float,
    height: float = 2.8,
    budget_level: str = "medium",
    use_llm: bool = False,
    **kwargs: Any,
) -> LayoutResponse:
    """Convenience function to generate a layout.

    Args:
        room_type: Type of room.
        width: Room width in meters.
        depth: Room depth in meters.
        height: Room height in meters.
        budget_level: Budget level.
        use_llm: Whether to use LLM for intelligent scoring.
        **kwargs: Additional request parameters.

    Returns:
        LayoutResponse with generated layout.
    """
    request = LayoutRequest(
        room_type=room_type,
        width=width,
        depth=depth,
        height=height,
        budget_level=budget_level,
        **{k: v for k, v in kwargs.items() if k in LayoutRequest.__dataclass_fields__},
    )

    config = OrchestratorConfig(use_llm=use_llm)
    orchestrator = LayoutOrchestrator(config)
    return await orchestrator.generate_layout(request)
