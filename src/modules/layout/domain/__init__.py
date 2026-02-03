"""Domain layer for feng shui layout module."""

from src.modules.layout.domain.entities import (
    DoorPosition,
    Furniture,
    FurnitureCategory,
    FurnitureDimensions,
    Placement,
    Room,
    RoomType,
    WallSide,
    WindowPosition,
)
from src.modules.layout.domain.value_objects import (
    BoundingBox,
    FengShuiScore,
    Position3D,
    Rotation,
    RulePriority,
)

__all__ = [
    # Entities
    "DoorPosition",
    "Furniture",
    "FurnitureCategory",
    "FurnitureDimensions",
    "Placement",
    "Room",
    "RoomType",
    "WallSide",
    "WindowPosition",
    # Value Objects
    "BoundingBox",
    "FengShuiScore",
    "Position3D",
    "Rotation",
    "RulePriority",
]
