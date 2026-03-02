"""Furniture entity for feng shui layout."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from src.modules.layout.domain.value_objects.coordinates import BoundingBox, Position3D


class FurnitureCategory(StrEnum):
    """Furniture categories."""

    # Bedroom
    BED = "bed"
    WARDROBE = "wardrobe"
    NIGHTSTAND = "nightstand"
    DRESSER = "dresser"

    # Living Room
    SOFA = "sofa"
    ARMCHAIR = "armchair"
    COFFEE_TABLE = "coffee_table"
    TV_STAND = "tv_stand"
    BOOKSHELF = "bookshelf"

    # Office
    DESK = "desk"
    OFFICE_CHAIR = "chair"
    FILING_CABINET = "filing_cabinet"

    # Dining Room
    DINING_TABLE = "dining_table"
    DINING_CHAIR = "dining_chair"
    SIDEBOARD = "sideboard"

    # General
    PLANT = "plant"
    LAMP = "lamp"
    RUG = "rug"

    @property
    def is_seating(self) -> bool:
        """Check if this is a seating furniture."""
        return self in (
            self.SOFA,
            self.ARMCHAIR,
            self.OFFICE_CHAIR,
            self.DINING_CHAIR,
        )

    @property
    def is_surface(self) -> bool:
        """Check if this is a surface/table furniture."""
        return self in (
            self.DESK,
            self.COFFEE_TABLE,
            self.DINING_TABLE,
            self.NIGHTSTAND,
            self.DRESSER,
            self.SIDEBOARD,
        )

    @property
    def needs_wall(self) -> bool:
        """Check if this furniture typically needs to be against a wall."""
        return self in (
            self.BED,
            self.WARDROBE,
            self.TV_STAND,
            self.BOOKSHELF,
            self.FILING_CABINET,
            self.SIDEBOARD,
            self.DRESSER,
        )


class FiveElement(StrEnum):
    """Five elements in feng shui."""

    WOOD = "wood"
    FIRE = "fire"
    EARTH = "earth"
    METAL = "metal"
    WATER = "water"

    @property
    def produces(self) -> FiveElement:
        """Get element this element produces (generative cycle)."""
        cycle = {
            self.WOOD: self.FIRE,
            self.FIRE: self.EARTH,
            self.EARTH: self.METAL,
            self.METAL: self.WATER,
            self.WATER: self.WOOD,
        }
        return cycle[self]

    @property
    def weakens(self) -> FiveElement:
        """Get element this element weakens (exhaustive cycle)."""
        cycle = {
            self.WOOD: self.WATER,
            self.FIRE: self.WOOD,
            self.EARTH: self.FIRE,
            self.METAL: self.EARTH,
            self.WATER: self.METAL,
        }
        return cycle[self]


@dataclass(frozen=True)
class FurnitureDimensions:
    """Physical dimensions of furniture.

    Attributes:
        width: Width (x-axis) in meters.
        depth: Depth (z-axis) in meters.
        height: Height (y-axis) in meters.
    """

    width: float
    depth: float
    height: float

    def __post_init__(self) -> None:
        """Validate dimensions are positive."""
        if self.width <= 0:
            msg = f"Width must be > 0, got {self.width}"
            raise ValueError(msg)
        if self.depth <= 0:
            msg = f"Depth must be > 0, got {self.depth}"
            raise ValueError(msg)
        if self.height <= 0:
            msg = f"Height must be > 0, got {self.height}"
            raise ValueError(msg)

    @property
    def floor_area(self) -> float:
        """Calculate floor area (width x depth)."""
        return self.width * self.depth

    @property
    def volume(self) -> float:
        """Calculate volume."""
        return self.width * self.depth * self.height

    def scale(self, factor: float) -> FurnitureDimensions:
        """Create scaled dimensions.

        Args:
            factor: Scale factor (e.g., 0.9 for 90%).

        Returns:
            New scaled dimensions.
        """
        return FurnitureDimensions(
            width=self.width * factor,
            depth=self.depth * factor,
            height=self.height * factor,
        )

    def fits_in(self, width: float, depth: float) -> bool:
        """Check if furniture fits in given floor space.

        Args:
            width: Available width.
            depth: Available depth.

        Returns:
            True if furniture fits (in either orientation).
        """
        # Check normal orientation
        if self.width <= width and self.depth <= depth:
            return True
        # Check rotated 90 degrees
        return self.depth <= width and self.width <= depth


@dataclass
class Furniture:
    """Furniture entity representing a catalog item.

    Attributes:
        id: Unique furniture identifier.
        name: Human-readable name.
        category: Furniture category.
        dimensions: Physical dimensions.
        min_clearance: Minimum clearance around furniture in meters.
        element: Associated feng shui element.
        is_essential: Whether this is essential for room type.
        model_url: Optional 3D model URL.
    """

    id: str
    name: str
    category: FurnitureCategory
    dimensions: FurnitureDimensions
    min_clearance: float = 0.6
    element: FiveElement = FiveElement.WOOD
    is_essential: bool = False
    model_url: str | None = None

    def __post_init__(self) -> None:
        """Validate furniture properties."""
        if not self.id:
            msg = "Furniture id cannot be empty"
            raise ValueError(msg)
        if self.min_clearance < 0:
            msg = f"min_clearance must be >= 0, got {self.min_clearance}"
            raise ValueError(msg)

    def get_bounding_box(self, position: Position3D) -> BoundingBox:
        """Get bounding box at given position.

        Args:
            position: Bottom-center position of furniture.

        Returns:
            BoundingBox representing furniture at position.
        """
        half_width = self.dimensions.width / 2
        half_depth = self.dimensions.depth / 2

        return BoundingBox(
            min_x=position.x - half_width,
            min_y=position.y,
            min_z=position.z - half_depth,
            max_x=position.x + half_width,
            max_y=position.y + self.dimensions.height,
            max_z=position.z + half_depth,
        )

    def get_clearance_box(self, position: Position3D) -> BoundingBox:
        """Get bounding box including clearance at given position.

        Args:
            position: Bottom-center position of furniture.

        Returns:
            BoundingBox including minimum clearance zone.
        """
        base_box = self.get_bounding_box(position)
        return base_box.expand(self.min_clearance)

    def fits_in_room(self, room_width: float, room_depth: float) -> bool:
        """Check if furniture can fit in room.

        Args:
            room_width: Room width in meters.
            room_depth: Room depth in meters.

        Returns:
            True if furniture fits (in either orientation).
        """
        return self.dimensions.fits_in(room_width, room_depth)

    @property
    def needs_wall_backing(self) -> bool:
        """Check if furniture typically needs wall backing."""
        return self.category.needs_wall
