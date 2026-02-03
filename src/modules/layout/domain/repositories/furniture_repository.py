"""Furniture repository interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.modules.layout.domain.entities.furniture import (
        Furniture,
        FurnitureCategory,
    )
    from src.modules.layout.domain.entities.room import RoomType


class FurnitureRepository(ABC):
    """Abstract repository for furniture catalog access.

    This interface defines the contract for accessing furniture data,
    whether from an in-memory catalog, database, or external service.

    Implementations should be stateless and thread-safe.
    """

    @abstractmethod
    async def get_by_id(self, furniture_id: str) -> Furniture | None:
        """Get furniture by ID.

        Args:
            furniture_id: Unique furniture identifier.

        Returns:
            Furniture if found, None otherwise.
        """
        ...

    @abstractmethod
    async def get_by_category(
        self,
        category: FurnitureCategory,
        limit: int = 20,
    ) -> list[Furniture]:
        """Get furniture by category.

        Args:
            category: Furniture category to filter by.
            limit: Maximum number of results.

        Returns:
            List of furniture in the category.
        """
        ...

    @abstractmethod
    async def get_for_room_type(
        self,
        room_type: RoomType,
        include_optional: bool = True,
        limit: int = 30,
    ) -> list[Furniture]:
        """Get furniture suitable for a room type.

        Args:
            room_type: Type of room to get furniture for.
            include_optional: Whether to include optional furniture.
            limit: Maximum number of results.

        Returns:
            List of furniture suitable for the room type.
        """
        ...

    @abstractmethod
    async def get_essential_for_room_type(
        self,
        room_type: RoomType,
    ) -> list[Furniture]:
        """Get essential furniture for a room type.

        Essential furniture are items that must be present in the room.

        Args:
            room_type: Type of room.

        Returns:
            List of essential furniture for the room type.
        """
        ...

    @abstractmethod
    async def search(
        self,
        query: str,
        room_type: RoomType | None = None,
        categories: list[FurnitureCategory] | None = None,
        max_width: float | None = None,
        max_depth: float | None = None,
        limit: int = 20,
    ) -> list[Furniture]:
        """Search furniture catalog.

        Args:
            query: Search query string.
            room_type: Optional room type filter.
            categories: Optional category filters.
            max_width: Maximum width constraint.
            max_depth: Maximum depth constraint.
            limit: Maximum number of results.

        Returns:
            List of matching furniture.
        """
        ...

    @abstractmethod
    async def get_alternatives(
        self,
        furniture_id: str,
        limit: int = 5,
    ) -> list[Furniture]:
        """Get alternative furniture options.

        Find similar furniture that could replace the given item.

        Args:
            furniture_id: ID of furniture to find alternatives for.
            limit: Maximum number of alternatives.

        Returns:
            List of alternative furniture options.
        """
        ...

    @abstractmethod
    async def get_smaller_variant(
        self,
        furniture_id: str,
    ) -> Furniture | None:
        """Get a smaller variant of the furniture.

        Useful when the original doesn't fit.

        Args:
            furniture_id: ID of furniture to find smaller variant for.

        Returns:
            Smaller variant if available, None otherwise.
        """
        ...

    @abstractmethod
    async def count_by_room_type(
        self,
        room_type: RoomType,
    ) -> int:
        """Count available furniture for a room type.

        Args:
            room_type: Type of room.

        Returns:
            Total count of available furniture.
        """
        ...
