"""Placement engine service for furniture placement."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from src.modules.layout.application.dtos import (
    AgentContext,
    PlacedFurniture,
    PlacementStrategy,
)
from src.modules.layout.application.dtos.placement_result import (
    BatchPlacementResult,
    FallbackAction,
    PlacementAttempt,
    PlacementFailureReason,
    PlacementResult,
    PlacementStatus,
)
from src.modules.layout.application.dtos.spatial_analysis import (
    CommandPosition,
    SpatialAnalysisResult,
    ZoneQuality,
)
from src.modules.layout.application.services.furniture_selector import (
    FurnitureSelection,
)
from src.modules.layout.infrastructure.geometry import (
    AABB,
    ClearanceRequirement,
    CollisionDetector,
    PlacementCandidate,
    PlacementGrid,
)


class RotationStrategy(str, Enum):
    """Strategies for rotation during placement."""

    FIXED = "fixed"  # No rotation
    FOUR_WAY = "four_way"  # Try 0, 90, 180, 270
    TWO_WAY = "two_way"  # Try 0, 90 only


class FallbackStrategy(str, Enum):
    """Fallback strategies when placement fails."""

    MOVE = "move"  # Try different positions
    ROTATE = "rotate"  # Try different rotations
    SKIP = "skip"  # Skip the item
    RESIZE = "resize"  # Try smaller alternative


@dataclass
class PlacementConfig:
    """Configuration for placement engine.

    Attributes:
        grid_cell_size: Size of grid cells in meters (default 0.1 = 10cm).
        min_clearance: Minimum clearance between items in meters.
        max_placement_attempts: Maximum attempts per item.
        rotation_strategy: How to handle rotation.
        fallback_order: Order of fallback strategies to try.
        max_occupancy_ratio: Maximum ratio of floor area to occupy.
        prefer_wall_placement: Whether to prefer wall-adjacent placements.
    """

    grid_cell_size: float = 0.1
    min_clearance: float = 0.6
    max_placement_attempts: int = 100
    rotation_strategy: RotationStrategy = RotationStrategy.FOUR_WAY
    fallback_order: list[FallbackStrategy] = field(
        default_factory=lambda: [
            FallbackStrategy.ROTATE,
            FallbackStrategy.MOVE,
            FallbackStrategy.SKIP,
        ]
    )
    max_occupancy_ratio: float = 0.7
    prefer_wall_placement: bool = True


class PlacementEngine:
    """Engine for placing furniture in a room.

    This service is responsible for:
    - Grid-based furniture placement
    - Collision detection and avoidance
    - Rotation strategies (0/90/180/270)
    - Fallback strategies (move/rotate/skip)
    - Feng shui position optimization
    """

    # Rotations to try based on strategy
    ROTATIONS = {
        RotationStrategy.FIXED: [0],
        RotationStrategy.TWO_WAY: [0, 90],
        RotationStrategy.FOUR_WAY: [0, 90, 180, 270],
    }

    # Category-specific placement preferences
    CATEGORY_PREFERENCES: dict[str, PlacementStrategy] = {
        "bed": PlacementStrategy.COMMAND_POSITION,
        "desk": PlacementStrategy.COMMAND_POSITION,
        "sofa": PlacementStrategy.WALL_ALIGNED,
        "dining_table": PlacementStrategy.CENTER_ROOM,
        "bookshelf": PlacementStrategy.WALL_ALIGNED,
        "wardrobe": PlacementStrategy.WALL_ALIGNED,
        "coffee_table": PlacementStrategy.CENTER_ROOM,
        "nightstand": PlacementStrategy.WALL_ALIGNED,
        "tv_stand": PlacementStrategy.WALL_ALIGNED,
    }

    def __init__(
        self,
        room_width: float,
        room_depth: float,
        config: PlacementConfig | None = None,
    ) -> None:
        """Initialize the placement engine.

        Args:
            room_width: Room width in meters.
            room_depth: Room depth in meters.
            config: Placement configuration.
        """
        self.room_width = room_width
        self.room_depth = room_depth
        self.config = config or PlacementConfig()

        # Initialize grid and collision detector
        self.grid = PlacementGrid(
            width=room_width,
            depth=room_depth,
            cell_size=self.config.grid_cell_size,
        )
        self.collision_detector = CollisionDetector(room_width, room_depth)

        # Track placed items
        self._placed_items: list[PlacedFurniture] = []
        self._placed_boxes: list[AABB] = []

    def place_all(
        self,
        selections: list[FurnitureSelection],
        spatial_analysis: SpatialAnalysisResult | None = None,
    ) -> BatchPlacementResult:
        """Place all selected furniture items.

        Args:
            selections: List of furniture selections to place.
            spatial_analysis: Spatial analysis result for optimization.

        Returns:
            BatchPlacementResult with all placement results.
        """
        start_time = time.time()
        result = BatchPlacementResult(total_items=len(selections))

        # Sort by priority (essential items first)
        sorted_selections = sorted(
            selections,
            key=lambda s: (0 if s.is_essential else 1, s.priority),
        )

        for selection in sorted_selections:
            placement_result = self.place_item(
                selection,
                spatial_analysis=spatial_analysis,
            )
            result.results.append(placement_result)

            if placement_result.is_success:
                result.placed_count += 1
            elif placement_result.status == PlacementStatus.FAILED:
                result.failed_count += 1
            else:
                result.skipped_count += 1

        # Determine overall status
        if result.placed_count == result.total_items:
            result.overall_status = PlacementStatus.SUCCESS
        elif result.placed_count == 0:
            result.overall_status = PlacementStatus.FAILED
        else:
            result.overall_status = PlacementStatus.PARTIAL

        result.execution_time_ms = (time.time() - start_time) * 1000
        return result

    def place_item(
        self,
        selection: FurnitureSelection,
        spatial_analysis: SpatialAnalysisResult | None = None,
    ) -> PlacementResult:
        """Place a single furniture item.

        Args:
            selection: Furniture selection to place.
            spatial_analysis: Spatial analysis for optimization.

        Returns:
            PlacementResult with placement details.
        """
        item = selection.item
        result = PlacementResult(
            furniture=None,
            status=PlacementStatus.FAILED,
        )

        # Get preferred strategy for this category
        strategy = self.CATEGORY_PREFERENCES.get(
            item.category,
            PlacementStrategy.GRID_BASED,
        )

        # Get rotations to try
        rotations = self.ROTATIONS[self.config.rotation_strategy]

        # Try to place with primary strategy
        placed = self._try_place_with_strategy(
            selection=selection,
            strategy=strategy,
            rotations=rotations,
            spatial_analysis=spatial_analysis,
            result=result,
        )

        if placed:
            return result

        # Apply fallback strategies
        for fallback in self.config.fallback_order:
            if result.is_success:
                break

            fallback_result = self._apply_fallback(
                selection=selection,
                fallback=fallback,
                rotations=rotations,
                spatial_analysis=spatial_analysis,
                result=result,
            )

            if fallback_result:
                result.status = PlacementStatus.SUCCESS
                break

        # If still failed and not essential, mark as skipped
        if not result.is_success and not selection.is_essential:
            result.status = PlacementStatus.SKIPPED

        return result

    def _try_place_with_strategy(
        self,
        selection: FurnitureSelection,
        strategy: PlacementStrategy,
        rotations: list[int],
        spatial_analysis: SpatialAnalysisResult | None,
        result: PlacementResult,
    ) -> bool:
        """Try to place item using a specific strategy.

        Args:
            selection: Furniture selection.
            strategy: Placement strategy to use.
            rotations: Rotations to try.
            spatial_analysis: Spatial analysis.
            result: PlacementResult to update.

        Returns:
            True if placement succeeded.
        """
        item = selection.item

        for rotation in rotations:
            # Get effective dimensions after rotation
            width, depth = self._get_rotated_dimensions(
                item.width,
                item.depth,
                rotation,
            )

            # Generate candidate positions based on strategy
            candidates = self._get_candidates_for_strategy(
                width=width,
                depth=depth,
                strategy=strategy,
                spatial_analysis=spatial_analysis,
                rotation=rotation,
            )

            for candidate in candidates:
                attempt = self._try_placement(
                    selection=selection,
                    x=candidate.world_x,
                    z=candidate.world_z,
                    rotation=rotation,
                    strategy=strategy,
                )
                result.attempts.append(attempt)

                if attempt.success:
                    # Create placed furniture
                    furniture = self._create_placed_furniture(
                        selection=selection,
                        x=candidate.world_x,
                        z=candidate.world_z,
                        rotation=rotation,
                        strategy=strategy,
                    )
                    result.furniture = furniture
                    result.status = PlacementStatus.SUCCESS
                    result.final_strategy = strategy

                    # Register placement
                    self._register_placement(furniture)
                    return True

                if len(result.attempts) >= self.config.max_placement_attempts:
                    return False

        return False

    def _try_placement(
        self,
        selection: FurnitureSelection,
        x: float,
        z: float,
        rotation: int,
        strategy: PlacementStrategy,
    ) -> PlacementAttempt:
        """Try to place item at a specific position.

        Args:
            selection: Furniture selection.
            x: X position.
            z: Z position.
            rotation: Rotation in degrees.
            strategy: Placement strategy.

        Returns:
            PlacementAttempt with result.
        """
        item = selection.item
        width, depth = self._get_rotated_dimensions(item.width, item.depth, rotation)

        # Create bounding box for the item
        item_box = AABB.from_position_and_size(x, z, width, depth)

        # Check room bounds
        bounds_result = self.collision_detector.check_room_bounds(item_box)
        if bounds_result.has_collision:
            return PlacementAttempt(
                furniture_id=item.id,
                furniture_name=item.name,
                pos_x=x,
                pos_z=z,
                rotation=rotation,
                strategy=strategy,
                success=False,
                failure_reason=PlacementFailureReason.OUT_OF_BOUNDS,
                message=bounds_result.message,
            )

        # Check collision with existing items
        for placed_box in self._placed_boxes:
            collision_result = self.collision_detector.check_collision(
                item_box, placed_box
            )
            if collision_result.has_collision:
                return PlacementAttempt(
                    furniture_id=item.id,
                    furniture_name=item.name,
                    pos_x=x,
                    pos_z=z,
                    rotation=rotation,
                    strategy=strategy,
                    success=False,
                    failure_reason=PlacementFailureReason.COLLISION,
                    message=collision_result.message,
                )

        # Check clearance
        clearance = ClearanceRequirement(
            front=item.clearance_front,
            back=0.1,
            left=item.clearance_sides,
            right=item.clearance_sides,
        )
        for placed_box in self._placed_boxes:
            clearance_result = self.collision_detector.check_clearance(
                item_box, placed_box, clearance, rotation
            )
            if clearance_result.has_collision:
                return PlacementAttempt(
                    furniture_id=item.id,
                    furniture_name=item.name,
                    pos_x=x,
                    pos_z=z,
                    rotation=rotation,
                    strategy=strategy,
                    success=False,
                    failure_reason=PlacementFailureReason.CLEARANCE_VIOLATION,
                    message=clearance_result.message,
                )

        # Check grid availability
        if not self.grid.is_rect_available(
            self.grid._item_rects.get(
                f"temp_{x}_{z}",
                self._world_to_grid_rect(x, z, width, depth),
            )
        ):
            # Try marking on grid
            if not self.grid.mark_occupied(
                f"_temp_check_{item.id}_{x}_{z}",
                x,
                z,
                width,
                depth,
            ):
                return PlacementAttempt(
                    furniture_id=item.id,
                    furniture_name=item.name,
                    pos_x=x,
                    pos_z=z,
                    rotation=rotation,
                    strategy=strategy,
                    success=False,
                    failure_reason=PlacementFailureReason.NO_SPACE,
                    message="Grid space not available",
                )
            # Remove temp check
            self.grid.remove_item(f"_temp_check_{item.id}_{x}_{z}")

        # Placement successful
        return PlacementAttempt(
            furniture_id=item.id,
            furniture_name=item.name,
            pos_x=x,
            pos_z=z,
            rotation=rotation,
            strategy=strategy,
            success=True,
            message="Placement successful",
        )

    def _apply_fallback(
        self,
        selection: FurnitureSelection,
        fallback: FallbackStrategy,
        rotations: list[int],
        spatial_analysis: SpatialAnalysisResult | None,
        result: PlacementResult,
    ) -> bool:
        """Apply a fallback strategy.

        Args:
            selection: Furniture selection.
            fallback: Fallback strategy to apply.
            rotations: Available rotations.
            spatial_analysis: Spatial analysis.
            result: PlacementResult to update.

        Returns:
            True if fallback succeeded.
        """
        item = selection.item

        if fallback == FallbackStrategy.ROTATE:
            # Try different rotations with grid-based strategy
            return self._try_place_with_strategy(
                selection=selection,
                strategy=PlacementStrategy.GRID_BASED,
                rotations=rotations,
                spatial_analysis=spatial_analysis,
                result=result,
            )

        elif fallback == FallbackStrategy.MOVE:
            # Try all available grid positions
            for rotation in rotations:
                width, depth = self._get_rotated_dimensions(
                    item.width, item.depth, rotation
                )

                candidates = self.grid.find_available_positions(
                    width=width,
                    depth=depth,
                    margin=self.config.min_clearance,
                )

                for candidate in candidates[:self.config.max_placement_attempts]:
                    attempt = self._try_placement(
                        selection=selection,
                        x=candidate.world_x,
                        z=candidate.world_z,
                        rotation=rotation,
                        strategy=PlacementStrategy.GRID_BASED,
                    )

                    # Record fallback action
                    fallback_action = FallbackAction(
                        action_type="move",
                        original_pos=(0, 0),
                        new_pos=(candidate.world_x, candidate.world_z),
                        original_rotation=0,
                        new_rotation=rotation,
                        reason="Primary position unavailable",
                        success=attempt.success,
                    )
                    result.fallback_actions.append(fallback_action)
                    result.attempts.append(attempt)

                    if attempt.success:
                        furniture = self._create_placed_furniture(
                            selection=selection,
                            x=candidate.world_x,
                            z=candidate.world_z,
                            rotation=rotation,
                            strategy=PlacementStrategy.GRID_BASED,
                        )
                        result.furniture = furniture
                        result.status = PlacementStatus.SUCCESS
                        result.final_strategy = PlacementStrategy.GRID_BASED
                        self._register_placement(furniture)
                        return True

        elif fallback == FallbackStrategy.SKIP:
            # Mark as skipped
            fallback_action = FallbackAction(
                action_type="skip",
                original_pos=(0, 0),
                new_pos=None,
                original_rotation=0,
                new_rotation=0,
                reason="No suitable position found",
                success=True,
            )
            result.fallback_actions.append(fallback_action)
            result.status = PlacementStatus.SKIPPED
            return False

        return False

    def _get_candidates_for_strategy(
        self,
        width: float,
        depth: float,
        strategy: PlacementStrategy,
        spatial_analysis: SpatialAnalysisResult | None,
        rotation: int,
    ) -> list[PlacementCandidate]:
        """Get candidate positions based on strategy.

        Args:
            width: Item width (after rotation).
            depth: Item depth (after rotation).
            strategy: Placement strategy.
            spatial_analysis: Spatial analysis.
            rotation: Current rotation.

        Returns:
            List of placement candidates.
        """
        candidates: list[PlacementCandidate] = []

        if strategy == PlacementStrategy.COMMAND_POSITION:
            candidates.extend(
                self._get_command_position_candidates(
                    width, depth, spatial_analysis, rotation
                )
            )

        elif strategy == PlacementStrategy.WALL_ALIGNED:
            candidates.extend(
                self._get_wall_aligned_candidates(width, depth, rotation)
            )

        elif strategy == PlacementStrategy.CENTER_ROOM:
            candidates.extend(
                self._get_center_room_candidates(width, depth, rotation)
            )

        elif strategy == PlacementStrategy.NEAR_WINDOW:
            candidates.extend(
                self._get_near_window_candidates(
                    width, depth, spatial_analysis, rotation
                )
            )

        # Always fall back to grid-based candidates
        if not candidates or strategy == PlacementStrategy.GRID_BASED:
            grid_candidates = self.grid.find_available_positions(
                width=width,
                depth=depth,
                margin=self.config.min_clearance / 2,
            )
            for c in grid_candidates:
                c.rotation = rotation
            candidates.extend(grid_candidates)

        # Sort by score (higher is better)
        candidates.sort(key=lambda c: c.score, reverse=True)
        return candidates[:self.config.max_placement_attempts]

    def _get_command_position_candidates(
        self,
        width: float,
        depth: float,
        spatial_analysis: SpatialAnalysisResult | None,
        rotation: int,
    ) -> list[PlacementCandidate]:
        """Get candidates for command position placement."""
        candidates: list[PlacementCandidate] = []

        if spatial_analysis and spatial_analysis.command_positions:
            for cmd_pos in spatial_analysis.command_positions:
                # Adjust position to place item with its back to the wall
                x = cmd_pos.x - width / 2
                z = cmd_pos.z - depth / 2

                # Ensure within bounds
                x = max(0, min(x, self.room_width - width))
                z = max(0, min(z, self.room_depth - depth))

                candidates.append(
                    PlacementCandidate(
                        position=self.grid._item_rects.get(
                            "temp",
                            self._world_to_grid_pos(x, z),
                        ),
                        world_x=x,
                        world_z=z,
                        score=cmd_pos.score,
                        rotation=rotation,
                    )
                )
        else:
            # Default command position: diagonal from door, near wall
            # Place near north wall, away from door (assuming door on south)
            x = self.room_width * 0.7 - width / 2
            z = 0.1  # Near north wall

            candidates.append(
                PlacementCandidate(
                    position=self._world_to_grid_pos(x, z),
                    world_x=x,
                    world_z=z,
                    score=80.0,
                    rotation=rotation,
                )
            )

        return candidates

    def _get_wall_aligned_candidates(
        self,
        width: float,
        depth: float,
        rotation: int,
    ) -> list[PlacementCandidate]:
        """Get candidates for wall-aligned placement."""
        candidates: list[PlacementCandidate] = []
        margin = self.config.min_clearance

        # North wall (z=0)
        for x in [margin, self.room_width / 2 - width / 2, self.room_width - width - margin]:
            if 0 <= x <= self.room_width - width:
                candidates.append(
                    PlacementCandidate(
                        position=self._world_to_grid_pos(x, margin),
                        world_x=x,
                        world_z=margin,
                        score=70.0 if x == self.room_width / 2 - width / 2 else 60.0,
                        rotation=rotation,
                    )
                )

        # South wall (z=room_depth)
        z = self.room_depth - depth - margin
        for x in [margin, self.room_width / 2 - width / 2, self.room_width - width - margin]:
            if 0 <= x <= self.room_width - width:
                candidates.append(
                    PlacementCandidate(
                        position=self._world_to_grid_pos(x, z),
                        world_x=x,
                        world_z=z,
                        score=50.0,  # Lower score - often near door
                        rotation=rotation,
                    )
                )

        # West wall (x=0)
        for z in [margin, self.room_depth / 2 - depth / 2, self.room_depth - depth - margin]:
            if 0 <= z <= self.room_depth - depth:
                candidates.append(
                    PlacementCandidate(
                        position=self._world_to_grid_pos(margin, z),
                        world_x=margin,
                        world_z=z,
                        score=55.0,
                        rotation=rotation,
                    )
                )

        # East wall (x=room_width)
        x = self.room_width - width - margin
        for z in [margin, self.room_depth / 2 - depth / 2, self.room_depth - depth - margin]:
            if 0 <= z <= self.room_depth - depth:
                candidates.append(
                    PlacementCandidate(
                        position=self._world_to_grid_pos(x, z),
                        world_x=x,
                        world_z=z,
                        score=55.0,
                        rotation=rotation,
                    )
                )

        return candidates

    def _get_center_room_candidates(
        self,
        width: float,
        depth: float,
        rotation: int,
    ) -> list[PlacementCandidate]:
        """Get candidates for center room placement."""
        candidates: list[PlacementCandidate] = []

        # Center of room
        center_x = self.room_width / 2 - width / 2
        center_z = self.room_depth / 2 - depth / 2

        candidates.append(
            PlacementCandidate(
                position=self._world_to_grid_pos(center_x, center_z),
                world_x=center_x,
                world_z=center_z,
                score=90.0,
                rotation=rotation,
            )
        )

        # Slightly off-center positions
        offsets = [(0.3, 0), (-0.3, 0), (0, 0.3), (0, -0.3)]
        for dx, dz in offsets:
            x = center_x + dx
            z = center_z + dz
            if (
                0 <= x <= self.room_width - width
                and 0 <= z <= self.room_depth - depth
            ):
                candidates.append(
                    PlacementCandidate(
                        position=self._world_to_grid_pos(x, z),
                        world_x=x,
                        world_z=z,
                        score=75.0,
                        rotation=rotation,
                    )
                )

        return candidates

    def _get_near_window_candidates(
        self,
        width: float,
        depth: float,
        spatial_analysis: SpatialAnalysisResult | None,
        rotation: int,
    ) -> list[PlacementCandidate]:
        """Get candidates near windows for natural light."""
        candidates: list[PlacementCandidate] = []

        if spatial_analysis and spatial_analysis.natural_light_zones:
            for zone in spatial_analysis.natural_light_zones:
                x = zone.x + zone.width / 2 - width / 2
                z = zone.z + zone.depth / 2 - depth / 2

                # Ensure within bounds
                x = max(0, min(x, self.room_width - width))
                z = max(0, min(z, self.room_depth - depth))

                score = 85.0 if zone.quality == ZoneQuality.EXCELLENT else 70.0

                candidates.append(
                    PlacementCandidate(
                        position=self._world_to_grid_pos(x, z),
                        world_x=x,
                        world_z=z,
                        score=score,
                        rotation=rotation,
                    )
                )

        return candidates

    def _create_placed_furniture(
        self,
        selection: FurnitureSelection,
        x: float,
        z: float,
        rotation: int,
        strategy: PlacementStrategy,
    ) -> PlacedFurniture:
        """Create a PlacedFurniture instance."""
        item = selection.item
        return PlacedFurniture(
            id=f"placed_{item.id}_{len(self._placed_items)}",
            furniture_id=item.id,
            name=item.name,
            category=item.category,
            pos_x=x,
            pos_z=z,
            width=item.width,
            depth=item.depth,
            height=item.height,
            rotation=rotation,
            is_essential=selection.is_essential,
            placement_strategy=strategy,
            feng_shui_notes=list(selection.feng_shui_notes),
        )

    def _register_placement(self, furniture: PlacedFurniture) -> None:
        """Register a placed furniture item."""
        self._placed_items.append(furniture)

        # Add bounding box
        width, depth = self._get_rotated_dimensions(
            furniture.width,
            furniture.depth,
            furniture.rotation,
        )
        box = AABB.from_position_and_size(
            furniture.pos_x,
            furniture.pos_z,
            width,
            depth,
        )
        self._placed_boxes.append(box)

        # Mark on grid
        self.grid.mark_occupied(
            furniture.id,
            furniture.pos_x,
            furniture.pos_z,
            width,
            depth,
        )

    def _get_rotated_dimensions(
        self,
        width: float,
        depth: float,
        rotation: int,
    ) -> tuple[float, float]:
        """Get dimensions after rotation."""
        if rotation in (90, 270):
            return depth, width
        return width, depth

    def _world_to_grid_pos(self, x: float, z: float) -> Any:
        """Convert world coordinates to grid position."""
        from src.modules.layout.infrastructure.geometry.grid import GridPosition

        return GridPosition.from_world(x, z, self.config.grid_cell_size)

    def _world_to_grid_rect(
        self,
        x: float,
        z: float,
        width: float,
        depth: float,
    ) -> Any:
        """Convert world rectangle to grid rectangle."""
        from src.modules.layout.infrastructure.geometry.grid import GridRect

        return GridRect.from_world_rect(x, z, width, depth, self.config.grid_cell_size)

    def get_placed_furniture(self) -> list[PlacedFurniture]:
        """Get all placed furniture."""
        return list(self._placed_items)

    def get_occupancy_rate(self) -> float:
        """Get current occupancy rate."""
        return self.grid.get_occupancy_rate()

    def get_available_area(self) -> float:
        """Get available floor area."""
        return self.grid.get_available_area()

    def clear(self) -> None:
        """Clear all placements."""
        self._placed_items.clear()
        self._placed_boxes.clear()
        self.grid.clear()

    def to_ascii(self) -> str:
        """Generate ASCII representation of current layout."""
        return self.grid.to_ascii()

    def update_context(
        self,
        context: AgentContext,
        result: BatchPlacementResult,
    ) -> None:
        """Update agent context with placement results.

        Args:
            context: Agent context to update.
            result: Batch placement result.
        """
        # Update placed furniture
        context.placed_furniture = list(self._placed_items)

        # Store metadata
        context.metadata["placement"] = {
            "total_items": result.total_items,
            "placed_count": result.placed_count,
            "failed_count": result.failed_count,
            "skipped_count": result.skipped_count,
            "success_rate": result.success_rate,
            "execution_time_ms": result.execution_time_ms,
            "occupancy_rate": self.get_occupancy_rate(),
        }

        # Add warnings for failed placements
        for r in result.get_failed_items():
            if r.attempts:
                last_attempt = r.attempts[-1]
                context.add_warning(
                    f"Failed to place {last_attempt.furniture_name}: "
                    f"{last_attempt.failure_reason.value if last_attempt.failure_reason else 'unknown'}"
                )
