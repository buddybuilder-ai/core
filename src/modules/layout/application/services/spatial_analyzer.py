"""Spatial analyzer service for room analysis."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.modules.layout.application.dtos import (
    AgentContext,
    AnalysisZone,
    CommandPosition,
    FengShuiDirection,
    SpatialAnalysisResult,
    TrafficFlowAnalysis,
    ZoneQuality,
)
from src.modules.layout.domain.entities import Room, WallSide


@dataclass
class SpatialAnalyzer:
    """Service for analyzing room spatial characteristics.

    This service is responsible for:
    - Calculating usable floor area
    - Identifying command positions (feng shui power positions)
    - Analyzing traffic flow and pathways
    - Identifying zones (work, rest, traffic, natural light)
    - Determining clearance requirements
    """

    # Minimum clearances in meters
    MIN_WALKING_PATH: float = 0.6  # 60cm
    MIN_DOOR_CLEARANCE: float = 0.9  # 90cm for door swing
    MIN_FURNITURE_CLEARANCE: float = 0.45  # 45cm around furniture

    # Command position parameters
    COMMAND_WALL_OFFSET: float = 0.3  # 30cm from back wall
    COMMAND_MIN_DOOR_DISTANCE: float = 1.5  # Must see door from 1.5m+
    COMMAND_MAX_DOOR_ANGLE: float = 90.0  # Can see door within 90 degrees

    # Zone sizes (relative to room)
    ZONE_MARGIN: float = 0.5  # 50cm margin from walls for zones

    def analyze(self, room: Room) -> SpatialAnalysisResult:
        """Analyze room spatial characteristics.

        Args:
            room: Room entity to analyze.

        Returns:
            SpatialAnalysisResult with analysis data.
        """
        # Calculate areas
        room_area = room.width * room.depth
        usable_area = self._calculate_usable_area(room)

        # Find command positions
        command_positions = self._find_command_positions(room)

        # Identify zones
        zones = self._identify_zones(room)

        # Analyze traffic flow
        traffic_flow = self._analyze_traffic_flow(room)

        return SpatialAnalysisResult(
            room_area=room_area,
            usable_area=usable_area,
            command_positions=command_positions,
            zones=zones,
            traffic_flow=traffic_flow,
        )

    def update_context(
        self,
        context: AgentContext,
        result: SpatialAnalysisResult,
    ) -> None:
        """Update agent context with spatial analysis results.

        Args:
            context: Agent context to update.
            result: Spatial analysis result.
        """
        context.metadata["spatial_analysis"] = {
            "room_area": result.room_area,
            "usable_area": result.usable_area,
            "usable_ratio": result.usable_ratio,
            "command_position_count": len(result.command_positions),
            "zone_count": len(result.zones),
            "has_clear_traffic_path": result.traffic_flow.has_clear_path
            if result.traffic_flow
            else False,
        }

        # Store best command position if available
        if result.best_command_position:
            context.metadata["best_command_position"] = {
                "x": result.best_command_position.x,
                "z": result.best_command_position.z,
                "facing": result.best_command_position.facing_direction.value,
                "score": result.best_command_position.score,
            }

    def _calculate_usable_area(self, room: Room) -> float:
        """Calculate usable floor area (excluding door swings and tight corners).

        Args:
            room: Room to analyze.

        Returns:
            Usable floor area in square meters.
        """
        total_area = room.width * room.depth

        # Subtract door swing areas
        door_area = 0.0
        for door in room.doors:
            # Approximate door swing as quarter circle
            door_area += (3.14159 * (door.width**2)) / 4

        # Subtract corners that are too tight for furniture
        # (very small rooms have proportionally less usable space)
        min_dimension = min(room.width, room.depth)
        if min_dimension < 3.0:
            corner_penalty = 0.1 * total_area  # 10% penalty for small rooms
        else:
            corner_penalty = 0.0

        usable = total_area - door_area - corner_penalty
        return max(usable, total_area * 0.5)  # At least 50% usable

    def _find_command_positions(self, room: Room) -> list[CommandPosition]:
        """Find feng shui command positions in the room.

        Command position principles:
        - Back against a solid wall (support)
        - Can see the door (awareness)
        - Not directly in line with the door (avoid sha chi)
        - Diagonal from the door is ideal

        Args:
            room: Room to analyze.

        Returns:
            List of command positions sorted by score (best first).
        """
        positions: list[CommandPosition] = []

        # Get door positions
        door_positions = self._get_door_center_positions(room)
        if not door_positions:
            # If no doors, use south wall center as default entry
            door_positions = [(room.width / 2, 0)]

        # Check each wall for potential command positions
        walls_to_check = [
            (WallSide.NORTH, self._get_north_wall_positions(room)),
            (WallSide.EAST, self._get_east_wall_positions(room)),
            (WallSide.WEST, self._get_west_wall_positions(room)),
        ]

        for wall, wall_positions in walls_to_check:
            for x, z in wall_positions:
                score, quality, can_see = self._score_command_position(
                    x, z, wall, door_positions, room
                )
                if score > 0:
                    facing = self._get_facing_direction(wall)
                    positions.append(
                        CommandPosition(
                            x=x,
                            z=z,
                            facing_direction=facing,
                            quality=quality,
                            has_solid_backing=True,
                            can_see_door=can_see,
                            score=score,
                        )
                    )

        # Sort by score (best first)
        positions.sort(key=lambda p: p.score, reverse=True)
        return positions[:5]  # Return top 5 positions

    def _get_door_center_positions(self, room: Room) -> list[tuple[float, float]]:
        """Get center positions of all doors.

        Args:
            room: Room with doors.

        Returns:
            List of (x, z) positions for door centers.
        """
        positions = []
        for door in room.doors:
            door_center = door.offset + door.width / 2
            if door.wall == WallSide.SOUTH:
                positions.append((door_center, 0))
            elif door.wall == WallSide.NORTH:
                positions.append((door_center, room.depth))
            elif door.wall == WallSide.WEST:
                positions.append((0, door_center))
            elif door.wall == WallSide.EAST:
                positions.append((room.width, door_center))
        return positions

    def _get_north_wall_positions(self, room: Room) -> list[tuple[float, float]]:
        """Get potential command positions along north wall.

        Args:
            room: Room to analyze.

        Returns:
            List of (x, z) positions.
        """
        z = room.depth - self.COMMAND_WALL_OFFSET
        # Check positions at 1/4, 1/2, 3/4 of wall
        positions = []
        for ratio in [0.25, 0.5, 0.75]:
            x = room.width * ratio
            positions.append((x, z))
        return positions

    def _get_east_wall_positions(self, room: Room) -> list[tuple[float, float]]:
        """Get potential command positions along east wall.

        Args:
            room: Room to analyze.

        Returns:
            List of (x, z) positions.
        """
        x = room.width - self.COMMAND_WALL_OFFSET
        positions = []
        for ratio in [0.25, 0.5, 0.75]:
            z = room.depth * ratio
            positions.append((x, z))
        return positions

    def _get_west_wall_positions(self, room: Room) -> list[tuple[float, float]]:
        """Get potential command positions along west wall.

        Args:
            room: Room to analyze.

        Returns:
            List of (x, z) positions.
        """
        x = self.COMMAND_WALL_OFFSET
        positions = []
        for ratio in [0.25, 0.5, 0.75]:
            z = room.depth * ratio
            positions.append((x, z))
        return positions

    def _score_command_position(
        self,
        x: float,
        z: float,
        wall: WallSide,
        door_positions: list[tuple[float, float]],
        room: Room,
    ) -> tuple[float, ZoneQuality, bool]:
        """Score a potential command position.

        Args:
            x: X coordinate.
            z: Z coordinate.
            wall: Wall the position is against.
            door_positions: List of door center positions.
            room: Room being analyzed.

        Returns:
            Tuple of (score 0-100, quality, can_see_door).
        """
        score = 0.0
        can_see_door = False

        # Check distance and angle to doors
        min_door_distance = float("inf")
        best_door_angle = 180.0

        for door_x, door_z in door_positions:
            dx = door_x - x
            dz = door_z - z
            distance = (dx**2 + dz**2) ** 0.5
            min_door_distance = min(min_door_distance, distance)

            # Calculate angle to door
            import math

            angle = abs(math.degrees(math.atan2(dx, dz)))
            best_door_angle = min(best_door_angle, angle)

        # Can see door if within reasonable angle
        can_see_door = best_door_angle < self.COMMAND_MAX_DOOR_ANGLE

        # Score based on feng shui principles
        # 1. Can see door (most important) - up to 40 points
        if can_see_door:
            score += 40

        # 2. Not directly in line with door - up to 30 points
        if min_door_distance > self.COMMAND_MIN_DOOR_DISTANCE:
            # Better if diagonal
            if 30 < best_door_angle < 60:
                score += 30  # Ideal diagonal
            elif 15 < best_door_angle < 75:
                score += 20  # Good angle
            else:
                score += 10  # Acceptable

        # 3. Distance from door - up to 20 points
        # Too close is bad, too far might not see
        if 2.0 <= min_door_distance <= 5.0:
            score += 20
        elif 1.5 <= min_door_distance < 2.0:
            score += 15
        elif min_door_distance > 5.0:
            score += 10

        # 4. Room coverage - up to 10 points
        # Position should have good view of room
        center_x = room.width / 2
        center_z = room.depth / 2
        distance_to_center = ((x - center_x) ** 2 + (z - center_z) ** 2) ** 0.5
        max_distance = ((room.width / 2) ** 2 + (room.depth / 2) ** 2) ** 0.5
        coverage_ratio = 1 - (distance_to_center / max_distance)
        score += coverage_ratio * 10

        # Determine quality based on score
        if score >= 80:
            quality = ZoneQuality.EXCELLENT
        elif score >= 50:
            quality = ZoneQuality.GOOD
        elif score >= 30:
            quality = ZoneQuality.ACCEPTABLE
        else:
            quality = ZoneQuality.POOR

        return score, quality, can_see_door

    def _get_facing_direction(self, wall: WallSide) -> FengShuiDirection:
        """Get facing direction when back is against wall.

        Args:
            wall: Wall the position is against.

        Returns:
            Direction the position faces.
        """
        mapping = {
            WallSide.NORTH: FengShuiDirection.SOUTH,
            WallSide.SOUTH: FengShuiDirection.NORTH,
            WallSide.EAST: FengShuiDirection.WEST,
            WallSide.WEST: FengShuiDirection.EAST,
        }
        return mapping.get(wall, FengShuiDirection.CENTER)

    def _identify_zones(self, room: Room) -> list[AnalysisZone]:
        """Identify functional zones in the room.

        Args:
            room: Room to analyze.

        Returns:
            List of identified zones.
        """
        zones: list[AnalysisZone] = []

        # Traffic zone (near doors)
        traffic_zones = self._identify_traffic_zones(room)
        zones.extend(traffic_zones)

        # Natural light zones (near windows)
        light_zones = self._identify_light_zones(room)
        zones.extend(light_zones)

        # Work/activity zone (well-lit, away from bed area)
        work_zone = self._identify_work_zone(room)
        if work_zone:
            zones.append(work_zone)

        # Rest zone (quieter, more private)
        rest_zone = self._identify_rest_zone(room)
        if rest_zone:
            zones.append(rest_zone)

        return zones

    def _identify_traffic_zones(self, room: Room) -> list[AnalysisZone]:
        """Identify traffic zones near doors.

        Args:
            room: Room to analyze.

        Returns:
            List of traffic zones.
        """
        zones = []
        for i, door in enumerate(room.doors):
            # Traffic zone is area in front of door
            zone_depth = 1.5  # 1.5m in front of door

            if door.wall == WallSide.SOUTH:
                x = max(0, door.offset - 0.15)
                z = 0
                w = min(door.width + 0.3, room.width - x)
                d = min(zone_depth, room.depth)
            elif door.wall == WallSide.NORTH:
                x = max(0, door.offset - 0.15)
                z = max(0, room.depth - zone_depth)
                w = min(door.width + 0.3, room.width - x)
                d = min(zone_depth, room.depth - z)
            elif door.wall == WallSide.WEST:
                x = 0
                z = max(0, door.offset - 0.15)
                w = min(zone_depth, room.width)
                d = min(door.width + 0.3, room.depth - z)
            else:  # EAST
                x = max(0, room.width - zone_depth)
                z = max(0, door.offset - 0.15)
                w = min(zone_depth, room.width - x)
                d = min(door.width + 0.3, room.depth - z)

            zones.append(
                AnalysisZone(
                    zone_type="traffic",
                    x=x,
                    z=z,
                    width=w,
                    depth=d,
                    quality=ZoneQuality.AVOID,  # Avoid placing furniture here
                    notes=[f"door_{i}"],
                )
            )

        return zones

    def _identify_light_zones(self, room: Room) -> list[AnalysisZone]:
        """Identify natural light zones near windows.

        Args:
            room: Room to analyze.

        Returns:
            List of natural light zones.
        """
        zones = []
        for i, window in enumerate(room.windows):
            # Light zone extends into room from window
            zone_depth = min(2.0, room.depth / 2)  # 2m or half room depth

            if window.wall == WallSide.SOUTH:
                x = max(0, window.offset - 0.3)
                z = 0
                w = min(window.width + 0.6, room.width - x)
                d = zone_depth
            elif window.wall == WallSide.NORTH:
                x = max(0, window.offset - 0.3)
                z = max(0, room.depth - zone_depth)
                w = min(window.width + 0.6, room.width - x)
                d = zone_depth
            elif window.wall == WallSide.WEST:
                x = 0
                z = max(0, window.offset - 0.3)
                w = zone_depth
                d = min(window.width + 0.6, room.depth - z)
            else:  # EAST
                x = max(0, room.width - zone_depth)
                z = max(0, window.offset - 0.3)
                w = zone_depth
                d = min(window.width + 0.6, room.depth - z)

            zones.append(
                AnalysisZone(
                    zone_type="natural_light",
                    x=x,
                    z=z,
                    width=w,
                    depth=d,
                    quality=ZoneQuality.GOOD,  # Good for work areas
                    notes=[f"window_{i}"],
                )
            )

        return zones

    def _identify_work_zone(self, room: Room) -> AnalysisZone | None:
        """Identify work/activity zone.

        Args:
            room: Room to analyze.

        Returns:
            Work zone or None if room too small.
        """
        if room.width < 3.0 or room.depth < 3.0:
            return None

        # Work zone near windows if available, otherwise near center
        if room.windows:
            # Find largest window
            largest_window = max(room.windows, key=lambda w: w.width)
            if largest_window.wall in (WallSide.SOUTH, WallSide.NORTH):
                x = max(0.5, largest_window.offset)
                w = min(2.5, largest_window.width + 1.0)
            else:
                x = room.width / 2 - 1.25
                w = 2.5

            z = room.depth / 2 - 1.0
            d = 2.0
        else:
            # Center of room
            x = room.width / 2 - 1.25
            z = room.depth / 2 - 1.0
            w = 2.5
            d = 2.0

        return AnalysisZone(
            zone_type="work",
            x=max(0, x),
            z=max(0, z),
            width=min(w, room.width - x),
            depth=min(d, room.depth - z),
            quality=ZoneQuality.GOOD,
        )

    def _identify_rest_zone(self, room: Room) -> AnalysisZone | None:
        """Identify rest zone (for bedroom) away from doors.

        Args:
            room: Room to analyze.

        Returns:
            Rest zone or None if room too small.
        """
        if room.width < 3.0 or room.depth < 3.0:
            return None

        # Rest zone is typically at the back of the room, away from door
        # Find the wall furthest from doors
        door_walls = {door.wall for door in room.doors}

        # Prefer north wall for rest (back of room)
        if WallSide.NORTH not in door_walls:
            x = self.ZONE_MARGIN
            z = room.depth - 2.5
            w = room.width - 2 * self.ZONE_MARGIN
            d = 2.0
        elif WallSide.WEST not in door_walls:
            x = self.ZONE_MARGIN
            z = self.ZONE_MARGIN
            w = 2.0
            d = room.depth - 2 * self.ZONE_MARGIN
        elif WallSide.EAST not in door_walls:
            x = room.width - 2.5
            z = self.ZONE_MARGIN
            w = 2.0
            d = room.depth - 2 * self.ZONE_MARGIN
        else:
            # All walls have doors, use center back
            x = room.width / 2 - 1.25
            z = room.depth / 2
            w = 2.5
            d = room.depth / 2 - self.ZONE_MARGIN

        return AnalysisZone(
            zone_type="rest",
            x=max(0, x),
            z=max(0, z),
            width=min(w, room.width - x),
            depth=min(d, room.depth - z),
            quality=ZoneQuality.EXCELLENT,
        )

    def _analyze_traffic_flow(self, room: Room) -> TrafficFlowAnalysis:
        """Analyze traffic flow in the room.

        Args:
            room: Room to analyze.

        Returns:
            Traffic flow analysis result.
        """
        # Calculate minimum path width between doors
        if len(room.doors) < 2:
            # Single door - measure path from door to opposite wall
            min_path_width = self._calculate_single_door_path_width(room)
            has_clear_path = min_path_width >= self.MIN_WALKING_PATH
        else:
            # Multiple doors - measure paths between them
            min_path_width = self._calculate_door_to_door_path_width(room)
            has_clear_path = min_path_width >= self.MIN_WALKING_PATH

        # Assess chi flow quality
        chi_quality = self._assess_chi_flow(room, min_path_width)

        return TrafficFlowAnalysis(
            main_path_width=min_path_width,
            has_clear_path=has_clear_path,
            chi_flow_quality=chi_quality,
            bottleneck_zones=[],  # Will be filled after furniture placement
        )

    def _calculate_single_door_path_width(self, room: Room) -> float:
        """Calculate path width for single-door room.

        Args:
            room: Room with single door.

        Returns:
            Available path width in meters.
        """
        if not room.doors:
            return min(room.width, room.depth)

        door = room.doors[0]
        # Path width depends on room dimension perpendicular to door wall
        if door.wall in (WallSide.NORTH, WallSide.SOUTH):
            return room.depth
        else:
            return room.width

    def _calculate_door_to_door_path_width(self, room: Room) -> float:
        """Calculate minimum path width between multiple doors.

        Args:
            room: Room with multiple doors.

        Returns:
            Minimum available path width.
        """
        min_width = float("inf")

        for i, door1 in enumerate(room.doors):
            for door2 in room.doors[i + 1 :]:
                # Calculate direct distance between doors
                pos1 = self._get_door_room_entry_point(door1, room)
                pos2 = self._get_door_room_entry_point(door2, room)

                dx = abs(pos1[0] - pos2[0])
                dz = abs(pos1[1] - pos2[1])

                # Minimum dimension for path
                if door1.wall == door2.wall:
                    # Same wall - path width is perpendicular dimension
                    if door1.wall in (WallSide.NORTH, WallSide.SOUTH):
                        min_width = min(min_width, room.depth)
                    else:
                        min_width = min(min_width, room.width)
                else:
                    # Different walls - use smaller of dx, dz
                    min_width = min(min_width, max(dx, dz))

        return min_width if min_width != float("inf") else min(room.width, room.depth)

    def _get_door_room_entry_point(self, door: Any, room: Room) -> tuple[float, float]:
        """Get the point where you enter the room from a door.

        Args:
            door: Door position.
            room: Room.

        Returns:
            (x, z) entry point.
        """
        door_center = door.offset + door.width / 2
        entry_offset = 0.5  # 50cm into room

        if door.wall == WallSide.SOUTH:
            return (door_center, entry_offset)
        elif door.wall == WallSide.NORTH:
            return (door_center, room.depth - entry_offset)
        elif door.wall == WallSide.WEST:
            return (entry_offset, door_center)
        else:  # EAST
            return (room.width - entry_offset, door_center)

    def _assess_chi_flow(self, room: Room, path_width: float) -> ZoneQuality:
        """Assess chi (energy) flow quality.

        Args:
            room: Room to analyze.
            path_width: Main traffic path width.

        Returns:
            Chi flow quality assessment.
        """
        # Chi flow principles:
        # - Good: Gentle, curved paths
        # - Bad: Direct lines between doors (sha chi)
        # - Bad: Blocked or stagnant areas

        # Check for direct door-to-door alignment (sha chi)
        has_sha_chi = self._check_sha_chi_alignment(room)

        # Assess based on path width and sha chi
        if has_sha_chi:
            return ZoneQuality.POOR
        elif path_width >= 1.0:
            return ZoneQuality.EXCELLENT
        elif path_width >= self.MIN_WALKING_PATH:
            return ZoneQuality.GOOD
        else:
            return ZoneQuality.ACCEPTABLE

    def _check_sha_chi_alignment(self, room: Room) -> bool:
        """Check if doors are directly aligned (creates sha chi).

        Args:
            room: Room to check.

        Returns:
            True if sha chi alignment exists.
        """
        if len(room.doors) < 2:
            return False

        for i, door1 in enumerate(room.doors):
            for door2 in room.doors[i + 1 :]:
                # Check if doors are on opposite walls and aligned
                if (
                    (door1.wall == WallSide.NORTH and door2.wall == WallSide.SOUTH)
                    or (door1.wall == WallSide.SOUTH and door2.wall == WallSide.NORTH)
                    or (door1.wall == WallSide.EAST and door2.wall == WallSide.WEST)
                    or (door1.wall == WallSide.WEST and door2.wall == WallSide.EAST)
                ):
                    # Check if they overlap horizontally
                    d1_start = door1.offset
                    d1_end = door1.offset + door1.width
                    d2_start = door2.offset
                    d2_end = door2.offset + door2.width

                    # If they overlap by more than 30%, it's sha chi
                    overlap_start = max(d1_start, d2_start)
                    overlap_end = min(d1_end, d2_end)
                    if overlap_end > overlap_start:
                        overlap = overlap_end - overlap_start
                        min_width = min(door1.width, door2.width)
                        if overlap / min_width > 0.3:
                            return True

        return False
