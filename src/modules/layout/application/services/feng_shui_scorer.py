"""Feng shui scorer service for layout evaluation."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from src.modules.layout.application.dtos import (
    AgentContext,
    PlacedFurniture,
)
from src.modules.layout.application.dtos.spatial_analysis import (
    CommandPosition,
    SpatialAnalysisResult,
)
from src.modules.layout.domain.entities import Room
from src.modules.layout.domain.value_objects import FengShuiScore
from src.modules.layout.infrastructure.geometry import AABB


class FengShuiElement(str, Enum):
    """Five elements of feng shui."""

    WOOD = "wood"
    FIRE = "fire"
    EARTH = "earth"
    METAL = "metal"
    WATER = "water"


@dataclass
class ScoringConfig:
    """Configuration for feng shui scoring.

    Attributes:
        command_position_weight: Weight for command position scoring.
        five_elements_weight: Weight for five elements balance.
        chi_flow_weight: Weight for chi flow scoring.
        sha_chi_weight: Weight for sha chi avoidance.
        min_door_distance: Minimum distance from door for command position.
        min_wall_distance: Minimum distance from walls.
        sha_chi_angle: Maximum angle for sha chi lines.
    """

    command_position_weight: float = 1.0
    five_elements_weight: float = 1.0
    chi_flow_weight: float = 1.0
    sha_chi_weight: float = 1.0
    min_door_distance: float = 1.0
    min_wall_distance: float = 0.3
    sha_chi_angle: float = 15.0  # degrees


@dataclass
class ScoringResult:
    """Result of feng shui scoring.

    Attributes:
        score: The computed feng shui score.
        component_details: Details for each scoring component.
        recommendations: Suggestions for improvement.
        warnings: Any warnings about the layout.
    """

    score: FengShuiScore
    component_details: dict[str, Any] = field(default_factory=dict)
    recommendations: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        """Get total score."""
        return self.score.total

    @property
    def grade(self) -> str:
        """Get grade."""
        return self.score.grade

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "score": {
                "total": self.score.total,
                "grade": self.score.grade,
                "command_position": self.score.command_position,
                "five_elements": self.score.five_elements,
                "chi_flow": self.score.chi_flow,
                "sha_chi_avoidance": self.score.sha_chi_avoidance,
            },
            "component_details": self.component_details,
            "recommendations": self.recommendations,
            "warnings": self.warnings,
        }


class FengShuiScorer:
    """Service for scoring layouts based on feng shui principles.

    This service evaluates:
    - Command position (0-30 points): Key furniture in power positions
    - Five elements (0-20 points): Balance of elements
    - Chi flow (0-25 points): Clear pathways, energy circulation
    - Sha chi avoidance (0-25 points): Avoiding negative energy patterns

    Total possible score: 100 points
    """

    # Key furniture categories that should be in command position
    COMMAND_POSITION_CATEGORIES = ["bed", "desk", "sofa"]

    # Element associations by category
    CATEGORY_ELEMENTS: dict[str, FengShuiElement] = {
        "bed": FengShuiElement.WOOD,
        "desk": FengShuiElement.WOOD,
        "chair": FengShuiElement.METAL,
        "sofa": FengShuiElement.EARTH,
        "bookshelf": FengShuiElement.WOOD,
        "wardrobe": FengShuiElement.WOOD,
        "nightstand": FengShuiElement.WOOD,
        "coffee_table": FengShuiElement.EARTH,
        "dining_table": FengShuiElement.EARTH,
        "tv_stand": FengShuiElement.METAL,
        "lamp": FengShuiElement.FIRE,
        "mirror": FengShuiElement.WATER,
        "plant": FengShuiElement.WOOD,
        "rug": FengShuiElement.EARTH,
    }

    # Ideal element balance (percentages)
    IDEAL_ELEMENT_BALANCE = {
        FengShuiElement.WOOD: 0.25,
        FengShuiElement.FIRE: 0.15,
        FengShuiElement.EARTH: 0.25,
        FengShuiElement.METAL: 0.20,
        FengShuiElement.WATER: 0.15,
    }

    def __init__(self, config: ScoringConfig | None = None) -> None:
        """Initialize the scorer.

        Args:
            config: Scoring configuration.
        """
        self.config = config or ScoringConfig()

    def score_layout(
        self,
        room: Room,
        placed_furniture: list[PlacedFurniture],
        spatial_analysis: SpatialAnalysisResult | None = None,
    ) -> ScoringResult:
        """Score a layout based on feng shui principles.

        Args:
            room: The room being scored.
            placed_furniture: List of placed furniture items.
            spatial_analysis: Optional spatial analysis result.

        Returns:
            ScoringResult with score and details.
        """
        result = ScoringResult(
            score=FengShuiScore.zero(),
            component_details={},
            recommendations=[],
            warnings=[],
        )

        if not placed_furniture:
            result.warnings.append("No furniture placed")
            return result

        # Calculate each component
        command_score, command_details = self._score_command_position(
            room, placed_furniture, spatial_analysis
        )
        elements_score, elements_details = self._score_five_elements(
            placed_furniture
        )
        chi_score, chi_details = self._score_chi_flow(
            room, placed_furniture, spatial_analysis
        )
        sha_chi_score, sha_chi_details = self._score_sha_chi_avoidance(
            room, placed_furniture
        )

        # Create final score
        result.score = FengShuiScore(
            command_position=command_score,
            five_elements=elements_score,
            chi_flow=chi_score,
            sha_chi_avoidance=sha_chi_score,
        )

        # Store component details
        result.component_details = {
            "command_position": command_details,
            "five_elements": elements_details,
            "chi_flow": chi_details,
            "sha_chi_avoidance": sha_chi_details,
        }

        # Generate recommendations
        result.recommendations = result.score.get_improvement_suggestions()

        return result

    def _score_command_position(
        self,
        room: Room,
        furniture: list[PlacedFurniture],
        spatial_analysis: SpatialAnalysisResult | None,
    ) -> tuple[int, dict[str, Any]]:
        """Score command position placement.

        Command position means:
        - Back against solid wall
        - Can see the door
        - Not in direct line with door
        - Diagonal from entrance
        """
        max_score = 30
        details: dict[str, Any] = {
            "items_evaluated": [],
            "items_in_command_position": [],
        }

        # Get key furniture items
        key_items = [
            f for f in furniture if f.category in self.COMMAND_POSITION_CATEGORIES
        ]

        if not key_items:
            details["reason"] = "No key furniture items found"
            return 15, details  # Neutral score

        total_item_score = 0
        items_evaluated = 0

        # Get command positions from spatial analysis
        command_positions: list[CommandPosition] = []
        if spatial_analysis and spatial_analysis.command_positions:
            command_positions = spatial_analysis.command_positions

        # Get door position (assume first door)
        door_x, door_z = self._get_door_position(room)

        for item in key_items:
            item_score = 0
            item_details: dict[str, Any] = {
                "category": item.category,
                "position": {"x": item.pos_x, "z": item.pos_z},
            }

            # Check if near command position
            if command_positions:
                min_dist = float("inf")
                for cmd_pos in command_positions:
                    dist = math.sqrt(
                        (item.center_x - cmd_pos.x) ** 2
                        + (item.center_z - cmd_pos.z) ** 2
                    )
                    min_dist = min(min_dist, dist)

                if min_dist < 1.0:  # Within 1m of command position
                    item_score += 10
                    item_details["near_command_position"] = True
                elif min_dist < 2.0:
                    item_score += 5
                    item_details["near_command_position"] = "partial"

            # Check for solid backing (near wall)
            has_solid_backing = self._has_solid_backing(room, item)
            if has_solid_backing:
                item_score += 8
                item_details["solid_backing"] = True

            # Check door visibility
            can_see_door = self._can_see_door(item, door_x, door_z, furniture)
            if can_see_door:
                item_score += 7
                item_details["can_see_door"] = True

            # Check not in direct line with door
            not_aligned = not self._is_aligned_with_door(item, door_x, door_z)
            if not_aligned:
                item_score += 5
                item_details["not_aligned_with_door"] = True

            details["items_evaluated"].append(item_details)
            total_item_score += item_score
            items_evaluated += 1

            if item_score >= 20:
                details["items_in_command_position"].append(item.category)

        # Average score across key items
        if items_evaluated > 0:
            avg_score = total_item_score / items_evaluated
            final_score = min(max_score, int(avg_score))
        else:
            final_score = 15

        details["average_item_score"] = (
            total_item_score / items_evaluated if items_evaluated else 0
        )
        return final_score, details

    def _score_five_elements(
        self,
        furniture: list[PlacedFurniture],
    ) -> tuple[int, dict[str, Any]]:
        """Score five elements balance.

        Good feng shui has balance among:
        - Wood: Growth, vitality
        - Fire: Passion, energy
        - Earth: Stability, grounding
        - Metal: Precision, clarity
        - Water: Flow, wisdom
        """
        max_score = 20
        details: dict[str, Any] = {
            "element_counts": {},
            "element_percentages": {},
        }

        # Count elements
        element_counts: dict[FengShuiElement, int] = dict.fromkeys(FengShuiElement, 0)

        for item in furniture:
            element = self.CATEGORY_ELEMENTS.get(
                item.category, FengShuiElement.EARTH
            )
            element_counts[element] += 1

        total_items = len(furniture)
        if total_items == 0:
            return 10, details  # Neutral score

        # Calculate percentages
        element_percentages: dict[FengShuiElement, float] = {
            elem: count / total_items for elem, count in element_counts.items()
        }

        details["element_counts"] = {e.value: c for e, c in element_counts.items()}
        details["element_percentages"] = {
            e.value: round(p * 100, 1) for e, p in element_percentages.items()
        }

        # Score based on balance
        # Calculate deviation from ideal balance
        total_deviation = 0
        elements_present = 0

        for element, ideal_pct in self.IDEAL_ELEMENT_BALANCE.items():
            actual_pct = element_percentages[element]
            deviation = abs(actual_pct - ideal_pct)
            total_deviation += deviation

            if element_counts[element] > 0:
                elements_present += 1

        # Score for variety (having multiple elements)
        variety_score = min(5, elements_present)

        # Score for balance (lower deviation is better)
        # Max deviation is 2.0 (all in one element)
        balance_ratio = 1 - (total_deviation / 2.0)
        balance_score = int(balance_ratio * 15)

        final_score = min(max_score, variety_score + balance_score)
        details["elements_present"] = elements_present
        details["balance_ratio"] = round(balance_ratio, 2)

        return final_score, details

    def _score_chi_flow(
        self,
        room: Room,
        furniture: list[PlacedFurniture],
        spatial_analysis: SpatialAnalysisResult | None,
    ) -> tuple[int, dict[str, Any]]:
        """Score chi (energy) flow.

        Good chi flow means:
        - Clear pathways through room
        - No blocked doorways
        - Gentle curves in traffic flow
        - Open center area
        """
        max_score = 25
        details: dict[str, Any] = {}

        # Calculate room occupancy
        room_area = room.width * room.depth
        furniture_area = sum(f.width * f.depth for f in furniture)
        occupancy_ratio = furniture_area / room_area

        details["occupancy_ratio"] = round(occupancy_ratio, 2)

        # Occupancy score (optimal is 40-60%)
        if 0.3 <= occupancy_ratio <= 0.6:
            occupancy_score = 8
        elif 0.2 <= occupancy_ratio <= 0.7:
            occupancy_score = 5
        else:
            occupancy_score = 2

        # Check for clear pathways
        pathway_score = self._score_pathways(room, furniture)
        details["pathway_score"] = pathway_score

        # Check traffic flow from spatial analysis
        traffic_score = 0
        if spatial_analysis and spatial_analysis.traffic_flow:
            tf = spatial_analysis.traffic_flow
            if tf.has_clear_path:
                traffic_score = 7
                details["has_clear_path"] = True
            elif tf.main_path_width >= 0.6:
                traffic_score = 4
                details["has_clear_path"] = "partial"
            else:
                details["has_clear_path"] = False

            if tf.bottleneck_zones:
                traffic_score -= len(tf.bottleneck_zones)
                details["bottlenecks"] = len(tf.bottleneck_zones)
        else:
            # Estimate traffic score without analysis
            traffic_score = 5

        # Center openness
        center_score = self._score_center_openness(room, furniture)
        details["center_openness_score"] = center_score

        final_score = min(
            max_score,
            occupancy_score + pathway_score + traffic_score + center_score,
        )
        return final_score, details

    def _score_sha_chi_avoidance(
        self,
        room: Room,
        furniture: list[PlacedFurniture],
    ) -> tuple[int, dict[str, Any]]:
        """Score sha chi (negative energy) avoidance.

        Good sha chi avoidance means:
        - No furniture directly in line with doors
        - Avoiding sharp corners pointing at key areas
        - Not blocking exits
        - No furniture with back to door
        """
        max_score = 25
        details: dict[str, Any] = {
            "issues": [],
        }

        door_x, door_z = self._get_door_position(room)
        issues_count = 0

        for item in furniture:
            # Check if directly aligned with door (poison arrow)
            if self._is_aligned_with_door(item, door_x, door_z):
                if item.category in self.COMMAND_POSITION_CATEGORIES:
                    issues_count += 2
                    details["issues"].append(
                        f"{item.name} is in direct line with door"
                    )
                else:
                    issues_count += 1

            # Check for back to door (vulnerable position)
            if item.category in self.COMMAND_POSITION_CATEGORIES:
                if self._has_back_to_door(item, door_x, door_z):
                    issues_count += 2
                    details["issues"].append(
                        f"{item.name} has back to door"
                    )

        # Check for blocked exits
        if self._is_exit_blocked(room, furniture, door_x, door_z):
            issues_count += 3
            details["issues"].append("Door exit is partially blocked")

        # Calculate score (fewer issues = higher score)
        penalty = min(max_score - 5, issues_count * 3)
        final_score = max(5, max_score - penalty)

        details["total_issues"] = issues_count
        return final_score, details

    def _get_door_position(self, room: Room) -> tuple[float, float]:
        """Get the primary door position."""
        if room.doors:
            door = room.doors[0]
            # Calculate door center based on wall and offset
            if door.wall == "north":
                return door.offset + door.width / 2, 0
            elif door.wall == "south":
                return door.offset + door.width / 2, room.depth
            elif door.wall == "west":
                return 0, door.offset + door.width / 2
            else:  # east
                return room.width, door.offset + door.width / 2

        # Default: door at center of south wall
        return room.width / 2, room.depth

    def _has_solid_backing(self, room: Room, item: PlacedFurniture) -> bool:
        """Check if item has solid wall backing."""
        threshold = 0.3  # Within 30cm of wall

        # Check each wall
        near_north = item.pos_z < threshold
        near_south = item.pos_z + item.depth > room.depth - threshold
        near_west = item.pos_x < threshold
        near_east = item.pos_x + item.width > room.width - threshold

        return near_north or near_south or near_west or near_east

    def _can_see_door(
        self,
        item: PlacedFurniture,
        door_x: float,
        door_z: float,
        all_furniture: list[PlacedFurniture],
    ) -> bool:
        """Check if item position can see the door."""
        # Create a line from item center to door
        item_center_x = item.center_x
        item_center_z = item.center_z

        # Check if any furniture blocks the view
        for other in all_furniture:
            if other.id == item.id:
                continue

            other_box = AABB.from_position_and_size(
                other.pos_x,
                other.pos_z,
                other.width,
                other.depth,
            )

            # Simple check: is the other item between this item and door?
            if self._blocks_line_of_sight(
                item_center_x, item_center_z,
                door_x, door_z,
                other_box,
            ):
                return False

        return True

    def _blocks_line_of_sight(
        self,
        start_x: float,
        start_z: float,
        end_x: float,
        end_z: float,
        box: AABB,
    ) -> bool:
        """Check if a box blocks line of sight."""
        # Simplified check: see if box is roughly between start and end
        min_x = min(start_x, end_x)
        max_x = max(start_x, end_x)
        min_z = min(start_z, end_z)
        max_z = max(start_z, end_z)

        # Check if box overlaps the bounding region
        # More detailed check would use line-box intersection
        return not (
            box.max_x < min_x
            or box.min_x > max_x
            or box.max_z < min_z
            or box.min_z > max_z
        )

    def _is_aligned_with_door(
        self,
        item: PlacedFurniture,
        door_x: float,
        door_z: float,
    ) -> bool:
        """Check if item is in direct line with door."""
        # Check X alignment (within 30% of item width)
        x_aligned = abs(item.center_x - door_x) < item.width * 0.5

        # Check Z alignment (within 30% of item depth)
        z_aligned = abs(item.center_z - door_z) < item.depth * 0.5

        return x_aligned or z_aligned

    def _has_back_to_door(
        self,
        item: PlacedFurniture,
        door_x: float,
        door_z: float,
    ) -> bool:
        """Check if item has its back facing the door."""
        # Determine item facing based on rotation
        # 0 degrees: facing south (back to north)
        # 90 degrees: facing west (back to east)
        # 180 degrees: facing north (back to south)
        # 270 degrees: facing east (back to west)

        item_center_x = item.center_x
        item_center_z = item.center_z

        # Calculate relative door position
        door_direction = math.atan2(door_z - item_center_z, door_x - item_center_x)
        door_direction_deg = math.degrees(door_direction)

        # Normalize to 0-360
        door_direction_deg = (door_direction_deg + 360) % 360

        # Check if door is behind (within 60 degrees of back direction)
        back_direction = (item.rotation + 180) % 360
        angle_diff = abs(door_direction_deg - back_direction)
        angle_diff = min(angle_diff, 360 - angle_diff)

        return angle_diff < 60

    def _is_exit_blocked(
        self,
        room: Room,
        furniture: list[PlacedFurniture],
        door_x: float,
        door_z: float,
    ) -> bool:
        """Check if door exit is blocked."""
        # Create door clearance zone (0.9m from door)
        clearance = 0.9
        door_zone = AABB.from_center_and_size(
            door_x, door_z, clearance * 2, clearance * 2
        )

        # Check if any furniture intersects the door zone
        for item in furniture:
            item_box = AABB.from_position_and_size(
                item.pos_x,
                item.pos_z,
                item.width,
                item.depth,
            )
            if item_box.intersects(door_zone):
                return True

        return False

    def _score_pathways(
        self,
        room: Room,
        furniture: list[PlacedFurniture],
    ) -> int:
        """Score pathway clarity."""
        # Check minimum gaps between furniture
        min_gap = float("inf")

        for i, item1 in enumerate(furniture):
            box1 = AABB.from_position_and_size(
                item1.pos_x, item1.pos_z, item1.width, item1.depth
            )
            for item2 in furniture[i + 1:]:
                box2 = AABB.from_position_and_size(
                    item2.pos_x, item2.pos_z, item2.width, item2.depth
                )
                gap = box1.distance_to(box2)
                if gap > 0:
                    min_gap = min(min_gap, gap)

        # Score based on minimum gap
        if min_gap == float("inf"):
            return 5  # Only one item or no items
        if min_gap >= 0.9:
            return 7  # Excellent pathways
        if min_gap >= 0.6:
            return 5  # Good pathways
        if min_gap >= 0.4:
            return 3  # Tight pathways
        return 1  # Very tight pathways

    def _score_center_openness(
        self,
        room: Room,
        furniture: list[PlacedFurniture],
    ) -> int:
        """Score how open the center of the room is."""
        # Define center zone (middle 30% of room)
        margin_x = room.width * 0.35
        margin_z = room.depth * 0.35
        center_zone = AABB(
            min_x=margin_x,
            min_z=margin_z,
            max_x=room.width - margin_x,
            max_z=room.depth - margin_z,
        )

        # Calculate furniture area in center
        center_area = center_zone.area
        furniture_in_center = 0

        for item in furniture:
            item_box = AABB.from_position_and_size(
                item.pos_x, item.pos_z, item.width, item.depth
            )
            intersection = center_zone.intersection(item_box)
            if intersection:
                furniture_in_center += intersection.area

        # Calculate center occupancy
        center_occupancy = furniture_in_center / center_area if center_area > 0 else 0

        # Score (less occupied center is better)
        if center_occupancy < 0.1:
            return 5  # Very open center
        if center_occupancy < 0.25:
            return 4  # Mostly open
        if center_occupancy < 0.4:
            return 2  # Moderately occupied
        return 1  # Center is crowded

    def update_context(
        self,
        context: AgentContext,
        result: ScoringResult,
    ) -> None:
        """Update agent context with scoring results.

        Args:
            context: Agent context to update.
            result: Scoring result.
        """
        context.feng_shui_score = result.score

        # Store metadata
        context.metadata["feng_shui_scoring"] = {
            "total_score": result.score.total,
            "grade": result.score.grade,
            "components": result.component_details,
            "recommendations": result.recommendations,
        }

        # Add warnings
        for warning in result.warnings:
            context.add_warning(warning)

        # Add validation warnings for low scores
        if result.score.total < 40:
            context.add_warning(
                f"Low feng shui score: {result.score.total}/100 (Grade: {result.score.grade})"
            )
