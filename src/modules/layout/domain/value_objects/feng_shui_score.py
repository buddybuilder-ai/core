"""Feng shui score value object."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FengShuiScore:
    """Immutable feng shui score breakdown.

    Scoring components:
    - command_position: 0-30 points (key furniture in command position)
    - five_elements: 0-20 points (balance of wood, fire, earth, metal, water)
    - chi_flow: 0-25 points (clear pathways, good energy circulation)
    - sha_chi_avoidance: 0-25 points (avoiding negative energy patterns)

    Total possible: 100 points
    """

    command_position: int
    five_elements: int
    chi_flow: int
    sha_chi_avoidance: int

    # Score ranges
    MAX_COMMAND_POSITION: int = 30
    MAX_FIVE_ELEMENTS: int = 20
    MAX_CHI_FLOW: int = 25
    MAX_SHA_CHI_AVOIDANCE: int = 25
    MAX_TOTAL: int = 100

    def __post_init__(self) -> None:
        """Validate score ranges."""
        self._validate_range("command_position", self.command_position, 0, 30)
        self._validate_range("five_elements", self.five_elements, 0, 20)
        self._validate_range("chi_flow", self.chi_flow, 0, 25)
        self._validate_range("sha_chi_avoidance", self.sha_chi_avoidance, 0, 25)

    @staticmethod
    def _validate_range(name: str, value: int, min_val: int, max_val: int) -> None:
        """Validate value is within range.

        Args:
            name: Field name for error message.
            value: Value to validate.
            min_val: Minimum allowed value.
            max_val: Maximum allowed value.

        Raises:
            ValueError: If value is out of range.
            TypeError: If value is not an integer.
        """
        if not isinstance(value, int):
            msg = f"{name} must be an integer, got {type(value).__name__}"
            raise TypeError(msg)
        if not min_val <= value <= max_val:
            msg = f"{name} must be between {min_val} and {max_val}, got {value}"
            raise ValueError(msg)

    @property
    def total(self) -> int:
        """Calculate total feng shui score (0-100)."""
        return self.command_position + self.five_elements + self.chi_flow + self.sha_chi_avoidance

    @property
    def percentage(self) -> float:
        """Calculate score as percentage (0-100%)."""
        return (self.total / self.MAX_TOTAL) * 100

    @property
    def grade(self) -> str:
        """Get letter grade based on total score.

        Returns:
            Grade string: A (>=90), B (>=70), C (>=50), D (>=40), F (<40)
        """
        total = self.total
        if total >= 90:
            return "A"
        if total >= 70:
            return "B"
        if total >= 50:
            return "C"
        if total >= 40:
            return "D"
        return "F"

    @property
    def is_acceptable(self) -> bool:
        """Check if score meets minimum acceptable threshold (>=40)."""
        return self.total >= 40

    @property
    def is_good(self) -> bool:
        """Check if score is considered good (>=70)."""
        return self.total >= 70

    @property
    def is_excellent(self) -> bool:
        """Check if score is excellent (>=90)."""
        return self.total >= 90

    def get_weakest_component(self) -> str:
        """Identify the component with lowest relative score.

        Returns:
            Name of the weakest scoring component.
        """
        # Calculate relative scores (0-1 scale)
        relative_scores = {
            "command_position": self.command_position / 30,
            "five_elements": self.five_elements / 20,
            "chi_flow": self.chi_flow / 25,
            "sha_chi_avoidance": self.sha_chi_avoidance / 25,
        }
        return min(relative_scores, key=lambda k: relative_scores[k])

    def get_improvement_suggestions(self) -> list[str]:
        """Get suggestions for improving the score.

        Returns:
            List of improvement suggestions for low-scoring components.
        """
        suggestions = []

        if self.command_position < 15:
            suggestions.append(
                "Move key furniture (bed/desk) to command position (back against wall, facing door)"
            )

        if self.five_elements < 10:
            suggestions.append(
                "Add elements to balance the five elements (wood, fire, earth, metal, water)"
            )

        if self.chi_flow < 12:
            suggestions.append("Clear pathways and remove obstacles to improve energy flow")

        if self.sha_chi_avoidance < 12:
            suggestions.append(
                "Address sharp corners (poison arrows) and "
                "avoid placing furniture in direct line with doors"
            )

        return suggestions

    @classmethod
    def zero(cls) -> FengShuiScore:
        """Create score with all zeros."""
        return cls(
            command_position=0,
            five_elements=0,
            chi_flow=0,
            sha_chi_avoidance=0,
        )

    @classmethod
    def perfect(cls) -> FengShuiScore:
        """Create perfect score (100 points)."""
        return cls(
            command_position=30,
            five_elements=20,
            chi_flow=25,
            sha_chi_avoidance=25,
        )
