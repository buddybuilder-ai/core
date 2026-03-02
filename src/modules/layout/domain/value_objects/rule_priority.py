"""Feng shui rule priority enumeration."""

from enum import IntEnum


class RulePriority(IntEnum):
    """Priority levels for feng shui rules.

    Level 1 (MUST_NOT_VIOLATE): Critical rules that cannot be broken
        - Bed must not face door directly
        - Desk must be able to see the door
        - No furniture blocking main walkways

    Level 2 (SHOULD_DO): Important rules that should be followed
        - Command position for key furniture
        - Wealth corner should be activated
        - Avoid beams over head

    Level 3 (RECOMMENDED): Nice-to-have recommendations
        - Balance of five elements
        - Color coordination by direction
        - Plants to enhance energy
    """

    MUST_NOT_VIOLATE = 1
    SHOULD_DO = 2
    RECOMMENDED = 3

    @property
    def description(self) -> str:
        """Get human-readable description of priority level."""
        descriptions = {
            self.MUST_NOT_VIOLATE: "Critical - Must not violate",
            self.SHOULD_DO: "Important - Should follow",
            self.RECOMMENDED: "Nice to have - Recommended",
        }
        return descriptions.get(self, "Unknown")

    @property
    def weight(self) -> float:
        """Get scoring weight for this priority level.

        Higher priority = higher weight.
        """
        weights = {
            self.MUST_NOT_VIOLATE: 1.0,
            self.SHOULD_DO: 0.6,
            self.RECOMMENDED: 0.3,
        }
        return weights.get(self, 0.0)

    def is_critical(self) -> bool:
        """Check if this is a critical (must not violate) rule."""
        return self == self.MUST_NOT_VIOLATE

    def is_important(self) -> bool:
        """Check if this is at least an important rule."""
        return self <= self.SHOULD_DO
