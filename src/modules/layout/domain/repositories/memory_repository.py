"""Agent memory repository interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class AgentMemoryEntry:
    """A single memory entry for the agent.

    Stores information about past layout generations
    for learning and improvement.
    """

    session_id: str
    timestamp: datetime
    room_type: str
    room_dimensions: dict[str, float]
    furniture_placed: list[str]
    feng_shui_score: int
    user_feedback: str | None = None
    adjustments_made: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "session_id": self.session_id,
            "timestamp": self.timestamp.isoformat(),
            "room_type": self.room_type,
            "room_dimensions": self.room_dimensions,
            "furniture_placed": self.furniture_placed,
            "feng_shui_score": self.feng_shui_score,
            "user_feedback": self.user_feedback,
            "adjustments_made": self.adjustments_made,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentMemoryEntry:
        """Create from dictionary."""
        return cls(
            session_id=data["session_id"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            room_type=data["room_type"],
            room_dimensions=data["room_dimensions"],
            furniture_placed=data["furniture_placed"],
            feng_shui_score=data["feng_shui_score"],
            user_feedback=data.get("user_feedback"),
            adjustments_made=data.get("adjustments_made", []),
            metadata=data.get("metadata", {}),
        )


@dataclass
class UserPreference:
    """User preference for layout generation."""

    user_id: str
    preference_key: str
    preference_value: Any
    created_at: datetime
    updated_at: datetime

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "user_id": self.user_id,
            "preference_key": self.preference_key,
            "preference_value": self.preference_value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


class AgentMemoryRepository(ABC):
    """Abstract repository for agent memory and user preferences.

    This interface defines the contract for persisting agent memory,
    including past layout generations, user feedback, and preferences.

    Memory is used for:
    - Learning from past generations
    - Remembering user preferences
    - Tracking successful patterns
    - Avoiding repeated mistakes
    """

    # =========================================================================
    # Memory Entry Operations
    # =========================================================================

    @abstractmethod
    async def save_memory(self, entry: AgentMemoryEntry) -> None:
        """Save a memory entry.

        Args:
            entry: Memory entry to save.
        """
        ...

    @abstractmethod
    async def get_memory(self, session_id: str) -> AgentMemoryEntry | None:
        """Get a memory entry by session ID.

        Args:
            session_id: Session ID to look up.

        Returns:
            Memory entry if found, None otherwise.
        """
        ...

    @abstractmethod
    async def get_recent_memories(
        self,
        room_type: str | None = None,
        limit: int = 10,
    ) -> list[AgentMemoryEntry]:
        """Get recent memory entries.

        Args:
            room_type: Optional filter by room type.
            limit: Maximum number of entries.

        Returns:
            List of recent memory entries, newest first.
        """
        ...

    @abstractmethod
    async def get_successful_patterns(
        self,
        room_type: str,
        min_score: int = 70,
        limit: int = 5,
    ) -> list[AgentMemoryEntry]:
        """Get successful layout patterns for a room type.

        Args:
            room_type: Room type to filter by.
            min_score: Minimum feng shui score threshold.
            limit: Maximum number of patterns.

        Returns:
            List of successful layout memories.
        """
        ...

    @abstractmethod
    async def update_feedback(
        self,
        session_id: str,
        feedback: str,
    ) -> bool:
        """Update user feedback for a session.

        Args:
            session_id: Session to update.
            feedback: User feedback text.

        Returns:
            True if updated successfully.
        """
        ...

    @abstractmethod
    async def delete_memory(self, session_id: str) -> bool:
        """Delete a memory entry.

        Args:
            session_id: Session ID to delete.

        Returns:
            True if deleted successfully.
        """
        ...

    # =========================================================================
    # User Preference Operations
    # =========================================================================

    @abstractmethod
    async def get_preference(
        self,
        user_id: str,
        preference_key: str,
    ) -> UserPreference | None:
        """Get a user preference.

        Args:
            user_id: User identifier.
            preference_key: Preference key.

        Returns:
            Preference if found, None otherwise.
        """
        ...

    @abstractmethod
    async def set_preference(
        self,
        user_id: str,
        preference_key: str,
        preference_value: Any,
    ) -> None:
        """Set a user preference.

        Creates if not exists, updates if exists.

        Args:
            user_id: User identifier.
            preference_key: Preference key.
            preference_value: Preference value.
        """
        ...

    @abstractmethod
    async def get_all_preferences(
        self,
        user_id: str,
    ) -> list[UserPreference]:
        """Get all preferences for a user.

        Args:
            user_id: User identifier.

        Returns:
            List of user preferences.
        """
        ...

    @abstractmethod
    async def delete_preference(
        self,
        user_id: str,
        preference_key: str,
    ) -> bool:
        """Delete a user preference.

        Args:
            user_id: User identifier.
            preference_key: Preference key.

        Returns:
            True if deleted successfully.
        """
        ...

    # =========================================================================
    # Statistics Operations
    # =========================================================================

    @abstractmethod
    async def get_average_score(
        self,
        room_type: str | None = None,
    ) -> float:
        """Get average feng shui score.

        Args:
            room_type: Optional room type filter.

        Returns:
            Average score across generations.
        """
        ...

    @abstractmethod
    async def get_generation_count(
        self,
        room_type: str | None = None,
    ) -> int:
        """Get total number of layout generations.

        Args:
            room_type: Optional room type filter.

        Returns:
            Total count of generations.
        """
        ...

    @abstractmethod
    async def get_most_used_furniture(
        self,
        room_type: str,
        limit: int = 10,
    ) -> list[tuple[str, int]]:
        """Get most frequently used furniture for a room type.

        Args:
            room_type: Room type to filter by.
            limit: Maximum number of results.

        Returns:
            List of (furniture_id, count) tuples.
        """
        ...

    # =========================================================================
    # Cleanup Operations
    # =========================================================================

    @abstractmethod
    async def cleanup_old_memories(
        self,
        days_old: int = 90,
    ) -> int:
        """Delete memories older than specified days.

        Args:
            days_old: Age threshold in days.

        Returns:
            Number of entries deleted.
        """
        ...
