"""Spatial analysis DTOs for feng shui layout generation."""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ZoneQuality(StrEnum):
    """Quality rating for zones."""

    EXCELLENT = "excellent"
    GOOD = "good"
    ACCEPTABLE = "acceptable"
    POOR = "poor"
    AVOID = "avoid"


class FengShuiDirection(StrEnum):
    """Feng shui cardinal directions."""

    NORTH = "north"
    SOUTH = "south"
    EAST = "east"
    WEST = "west"
    NORTHEAST = "northeast"
    NORTHWEST = "northwest"
    SOUTHEAST = "southeast"
    SOUTHWEST = "southwest"
    CENTER = "center"


@dataclass(frozen=True)
class AnalysisZone:
    """A zone identified during spatial analysis.

    Attributes:
        zone_type: Type of zone (command, traffic, window, etc.).
        x: X coordinate of zone start.
        z: Z coordinate of zone start.
        width: Zone width in meters.
        depth: Zone depth in meters.
        quality: Quality rating for furniture placement.
        feng_shui_direction: Associated feng shui direction.
        notes: Additional notes about the zone.
    """

    zone_type: str
    x: float
    z: float
    width: float
    depth: float
    quality: ZoneQuality = ZoneQuality.ACCEPTABLE
    feng_shui_direction: FengShuiDirection = FengShuiDirection.CENTER
    notes: list[str] = field(default_factory=list)

    @property
    def area(self) -> float:
        """Calculate zone area."""
        return self.width * self.depth

    @property
    def center_x(self) -> float:
        """Get center X coordinate."""
        return self.x + self.width / 2

    @property
    def center_z(self) -> float:
        """Get center Z coordinate."""
        return self.z + self.depth / 2

    def contains_point(self, x: float, z: float) -> bool:
        """Check if a point is within this zone."""
        return (
            self.x <= x <= self.x + self.width
            and self.z <= z <= self.z + self.depth
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "zone_type": self.zone_type,
            "position": {"x": self.x, "z": self.z},
            "dimensions": {"width": self.width, "depth": self.depth},
            "quality": self.quality.value,
            "feng_shui_direction": self.feng_shui_direction.value,
            "notes": list(self.notes),
        }


@dataclass(frozen=True)
class CommandPosition:
    """The command position in feng shui.

    The command position is the power position in a room, typically
    diagonal from the door with a solid wall behind.

    Attributes:
        x: X coordinate.
        z: Z coordinate.
        facing_direction: Direction the position faces.
        quality: Quality of this command position.
        has_solid_backing: Whether there's a solid wall behind.
        can_see_door: Whether the door is visible from here.
        score: Score for this position (0-100).
    """

    x: float
    z: float
    facing_direction: FengShuiDirection
    quality: ZoneQuality
    has_solid_backing: bool = True
    can_see_door: bool = True
    score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "position": {"x": self.x, "z": self.z},
            "facing_direction": self.facing_direction.value,
            "quality": self.quality.value,
            "has_solid_backing": self.has_solid_backing,
            "can_see_door": self.can_see_door,
            "score": self.score,
        }


@dataclass(frozen=True)
class TrafficFlowAnalysis:
    """Analysis of traffic flow patterns in the room.

    Attributes:
        main_path_width: Width of main traffic path.
        has_clear_path: Whether there's a clear path through room.
        door_to_door_distance: Distance between doors if multiple.
        bottleneck_zones: Zones with restricted flow.
        chi_flow_quality: Quality of chi energy flow.
    """

    main_path_width: float
    has_clear_path: bool
    door_to_door_distance: float | None = None
    bottleneck_zones: list[tuple[float, float]] = field(default_factory=list)
    chi_flow_quality: ZoneQuality = ZoneQuality.GOOD

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "main_path_width": self.main_path_width,
            "has_clear_path": self.has_clear_path,
            "door_to_door_distance": self.door_to_door_distance,
            "bottleneck_zones": self.bottleneck_zones,
            "chi_flow_quality": self.chi_flow_quality.value,
        }


@dataclass
class SpatialAnalysisResult:
    """Complete result of spatial analysis.

    Attributes:
        room_area: Total room area in square meters.
        usable_area: Usable area after excluding blocked zones.
        command_positions: Identified command positions.
        zones: All identified zones.
        traffic_flow: Traffic flow analysis.
        natural_light_zones: Zones with good natural light.
        privacy_zones: Zones with good privacy.
        avoid_zones: Zones to avoid for furniture.
        feng_shui_recommendations: List of feng shui recommendations.
    """

    room_area: float
    usable_area: float
    command_positions: list[CommandPosition] = field(default_factory=list)
    zones: list[AnalysisZone] = field(default_factory=list)
    traffic_flow: TrafficFlowAnalysis | None = None
    natural_light_zones: list[AnalysisZone] = field(default_factory=list)
    privacy_zones: list[AnalysisZone] = field(default_factory=list)
    avoid_zones: list[AnalysisZone] = field(default_factory=list)
    feng_shui_recommendations: list[str] = field(default_factory=list)

    @property
    def usable_ratio(self) -> float:
        """Get ratio of usable to total area."""
        return self.usable_area / self.room_area if self.room_area > 0 else 0

    @property
    def best_command_position(self) -> CommandPosition | None:
        """Get the best command position."""
        if not self.command_positions:
            return None
        return max(self.command_positions, key=lambda p: p.score)

    def get_zones_by_type(self, zone_type: str) -> list[AnalysisZone]:
        """Get zones of a specific type."""
        return [z for z in self.zones if z.zone_type == zone_type]

    def get_zones_by_quality(self, quality: ZoneQuality) -> list[AnalysisZone]:
        """Get zones of a specific quality."""
        return [z for z in self.zones if z.quality == quality]

    def is_position_in_avoid_zone(self, x: float, z: float) -> bool:
        """Check if a position is in an avoid zone."""
        return any(zone.contains_point(x, z) for zone in self.avoid_zones)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "room_area": self.room_area,
            "usable_area": self.usable_area,
            "usable_ratio": self.usable_ratio,
            "command_positions": [p.to_dict() for p in self.command_positions],
            "zones": [z.to_dict() for z in self.zones],
            "traffic_flow": self.traffic_flow.to_dict() if self.traffic_flow else None,
            "natural_light_zones": [z.to_dict() for z in self.natural_light_zones],
            "privacy_zones": [z.to_dict() for z in self.privacy_zones],
            "avoid_zones": [z.to_dict() for z in self.avoid_zones],
            "feng_shui_recommendations": self.feng_shui_recommendations,
        }
