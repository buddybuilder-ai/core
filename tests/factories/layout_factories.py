"""Test factories for layout module test data generation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.modules.layout.application.agent import LayoutRequest
from src.modules.layout.application.dtos import (
    AgentContext,
    PlacedFurniture,
    PlacementStrategy,
    UserPreferences,
)
from src.modules.layout.domain.entities import Room, RoomType


@dataclass
class RoomFactory:
    """Factory for creating Room test fixtures."""

    @staticmethod
    def create_bedroom(
        width: float = 5.0,
        depth: float = 4.0,
        height: float = 2.8,
    ) -> Room:
        """Create a bedroom room fixture."""
        return Room(
            width=width,
            depth=depth,
            height=height,
            room_type=RoomType.BEDROOM,
        )

    @staticmethod
    def create_office(
        width: float = 4.0,
        depth: float = 3.0,
        height: float = 2.8,
    ) -> Room:
        """Create an office room fixture."""
        return Room(
            width=width,
            depth=depth,
            height=height,
            room_type=RoomType.OFFICE,
        )

    @staticmethod
    def create_living_room(
        width: float = 6.0,
        depth: float = 5.0,
        height: float = 2.8,
    ) -> Room:
        """Create a living room fixture."""
        return Room(
            width=width,
            depth=depth,
            height=height,
            room_type=RoomType.LIVING_ROOM,
        )

    @staticmethod
    def create_dining_room(
        width: float = 4.5,
        depth: float = 4.0,
        height: float = 2.8,
    ) -> Room:
        """Create a dining room fixture."""
        return Room(
            width=width,
            depth=depth,
            height=height,
            room_type=RoomType.DINING_ROOM,
        )

    @staticmethod
    def create_small_room(
        room_type: RoomType = RoomType.BEDROOM,
    ) -> Room:
        """Create a small room fixture (2.5m x 2.5m)."""
        return Room(
            width=2.5,
            depth=2.5,
            height=2.4,
            room_type=room_type,
        )

    @staticmethod
    def create_large_room(
        room_type: RoomType = RoomType.LIVING_ROOM,
    ) -> Room:
        """Create a large room fixture (8m x 6m)."""
        return Room(
            width=8.0,
            depth=6.0,
            height=3.0,
            room_type=room_type,
        )


@dataclass
class LayoutRequestFactory:
    """Factory for creating LayoutRequest test fixtures."""

    @staticmethod
    def create_bedroom_request(
        width: float = 5.0,
        depth: float = 4.0,
        budget_level: str = "medium",
        max_furniture_items: int = 5,
    ) -> LayoutRequest:
        """Create a bedroom layout request."""
        return LayoutRequest(
            room_type="bedroom",
            width=width,
            depth=depth,
            height=2.8,
            budget_level=budget_level,
            max_furniture_items=max_furniture_items,
        )

    @staticmethod
    def create_office_request(
        width: float = 4.0,
        depth: float = 3.0,
        budget_level: str = "medium",
        max_furniture_items: int = 5,
    ) -> LayoutRequest:
        """Create an office layout request."""
        return LayoutRequest(
            room_type="office",
            width=width,
            depth=depth,
            height=2.8,
            budget_level=budget_level,
            max_furniture_items=max_furniture_items,
        )

    @staticmethod
    def create_living_room_request(
        width: float = 6.0,
        depth: float = 5.0,
        budget_level: str = "medium",
        max_furniture_items: int = 8,
    ) -> LayoutRequest:
        """Create a living room layout request."""
        return LayoutRequest(
            room_type="living_room",
            width=width,
            depth=depth,
            height=2.8,
            budget_level=budget_level,
            max_furniture_items=max_furniture_items,
        )

    @staticmethod
    def create_request_with_doors_and_windows() -> LayoutRequest:
        """Create a request with doors and windows."""
        return LayoutRequest(
            room_type="bedroom",
            width=5.0,
            depth=4.0,
            height=2.8,
            budget_level="medium",
            doors=[
                {"wall": "south", "offset": 2.0, "width": 0.9},
            ],
            windows=[
                {"wall": "east", "offset": 1.5, "width": 1.5},
            ],
        )


@dataclass
class PlacedFurnitureFactory:
    """Factory for creating PlacedFurniture test fixtures."""

    _counter: int = field(default=0, init=False)

    def _next_id(self) -> str:
        """Generate next unique ID."""
        self._counter += 1
        return f"furniture_{self._counter:03d}"

    def create_bed(
        self,
        pos_x: float = 1.5,
        pos_z: float = 0.3,
        rotation: int = 0,
    ) -> PlacedFurniture:
        """Create a placed bed fixture."""
        return PlacedFurniture(
            id=self._next_id(),
            furniture_id="bed_001",
            name="Queen Bed",
            category="bed",
            pos_x=pos_x,
            pos_z=pos_z,
            width=1.6,
            depth=2.0,
            height=0.5,
            rotation=rotation,
            is_essential=True,
            placement_strategy=PlacementStrategy.COMMAND_POSITION,
        )

    def create_desk(
        self,
        pos_x: float = 0.3,
        pos_z: float = 0.3,
        rotation: int = 0,
    ) -> PlacedFurniture:
        """Create a placed desk fixture."""
        return PlacedFurniture(
            id=self._next_id(),
            furniture_id="desk_001",
            name="Office Desk",
            category="desk",
            pos_x=pos_x,
            pos_z=pos_z,
            width=1.4,
            depth=0.7,
            height=0.75,
            rotation=rotation,
            is_essential=True,
            placement_strategy=PlacementStrategy.WALL_ALIGNED,
        )

    def create_chair(
        self,
        pos_x: float = 0.5,
        pos_z: float = 1.2,
        rotation: int = 0,
    ) -> PlacedFurniture:
        """Create a placed chair fixture."""
        return PlacedFurniture(
            id=self._next_id(),
            furniture_id="chair_001",
            name="Office Chair",
            category="chair",
            pos_x=pos_x,
            pos_z=pos_z,
            width=0.6,
            depth=0.6,
            height=1.0,
            rotation=rotation,
            is_essential=True,
            placement_strategy=PlacementStrategy.GRID_BASED,
        )

    def create_nightstand(
        self,
        pos_x: float = 0.3,
        pos_z: float = 0.3,
        rotation: int = 0,
    ) -> PlacedFurniture:
        """Create a placed nightstand fixture."""
        return PlacedFurniture(
            id=self._next_id(),
            furniture_id="nightstand_001",
            name="Nightstand",
            category="nightstand",
            pos_x=pos_x,
            pos_z=pos_z,
            width=0.5,
            depth=0.4,
            height=0.55,
            rotation=rotation,
            is_essential=False,
            placement_strategy=PlacementStrategy.WALL_ALIGNED,
        )

    def create_sofa(
        self,
        pos_x: float = 1.0,
        pos_z: float = 0.3,
        rotation: int = 0,
    ) -> PlacedFurniture:
        """Create a placed sofa fixture."""
        return PlacedFurniture(
            id=self._next_id(),
            furniture_id="sofa_001",
            name="3-Seater Sofa",
            category="sofa",
            pos_x=pos_x,
            pos_z=pos_z,
            width=2.2,
            depth=0.9,
            height=0.85,
            rotation=rotation,
            is_essential=True,
            placement_strategy=PlacementStrategy.CENTER_ROOM,
        )


@dataclass
class AgentContextFactory:
    """Factory for creating AgentContext test fixtures."""

    @staticmethod
    def create_bedroom_context(
        furniture_factory: PlacedFurnitureFactory | None = None,
    ) -> AgentContext:
        """Create a bedroom agent context with furniture."""
        room = RoomFactory.create_bedroom()
        context = AgentContext(
            room=room,
            room_type="bedroom",
            user_preferences=UserPreferences(budget_level="medium"),
        )

        if furniture_factory:
            context.placed_furniture = [
                furniture_factory.create_bed(),
                furniture_factory.create_nightstand(pos_x=0.1, pos_z=0.3),
            ]

        return context

    @staticmethod
    def create_office_context(
        furniture_factory: PlacedFurnitureFactory | None = None,
    ) -> AgentContext:
        """Create an office agent context with furniture."""
        room = RoomFactory.create_office()
        context = AgentContext(
            room=room,
            room_type="office",
            user_preferences=UserPreferences(budget_level="medium"),
        )

        if furniture_factory:
            context.placed_furniture = [
                furniture_factory.create_desk(),
                furniture_factory.create_chair(pos_x=0.8, pos_z=1.0),
            ]

        return context
