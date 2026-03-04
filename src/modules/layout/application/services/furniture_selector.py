"""Furniture selector service for room furnishing."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.modules.layout.application.dtos import (
    AgentContext,
    UserPreferences,
)
from src.modules.layout.infrastructure.tools import (
    FURNITURE_CATALOG,
    BudgetLevel,
    FurnitureCategory,
    FurnitureSearchInput,
    FurnitureSearchResult,
    InMemoryFurnitureDbTool,
)


@dataclass
class FurnitureSelection:
    """A furniture item selected for placement.

    Attributes:
        item: The furniture item from catalog.
        priority: Priority for placement (1 = highest).
        is_essential: Whether this is essential furniture.
        feng_shui_notes: Notes about feng shui placement.
        alternative_ids: Alternative furniture IDs if this doesn't fit.
    """

    item: FurnitureSearchResult
    priority: int
    is_essential: bool = False
    feng_shui_notes: list[str] = field(default_factory=list)
    alternative_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.item.id,
            "name": self.item.name,
            "category": self.item.category,
            "dimensions": {
                "width": self.item.width,
                "depth": self.item.depth,
                "height": self.item.height,
            },
            "priority": self.priority,
            "is_essential": self.is_essential,
            "feng_shui_notes": self.feng_shui_notes,
        }


@dataclass
class FurnitureSelectionResult:
    """Result of furniture selection.

    Attributes:
        selections: List of selected furniture.
        total_area_needed: Total floor area needed for all furniture.
        warnings: Any warnings during selection.
        skipped_items: Items that couldn't be selected.
    """

    selections: list[FurnitureSelection] = field(default_factory=list)
    total_area_needed: float = 0.0
    warnings: list[str] = field(default_factory=list)
    skipped_items: list[str] = field(default_factory=list)

    @property
    def essential_count(self) -> int:
        """Count of essential furniture items."""
        return sum(1 for s in self.selections if s.is_essential)

    @property
    def optional_count(self) -> int:
        """Count of optional furniture items."""
        return sum(1 for s in self.selections if not s.is_essential)

    def get_by_priority(self) -> list[FurnitureSelection]:
        """Get selections sorted by priority."""
        return sorted(self.selections, key=lambda s: s.priority)

    def get_essential(self) -> list[FurnitureSelection]:
        """Get only essential furniture."""
        return [s for s in self.selections if s.is_essential]

    def get_by_category(self, category: str) -> list[FurnitureSelection]:
        """Get selections by category."""
        return [s for s in self.selections if s.item.category == category]


class FurnitureSelector:
    """Service for selecting appropriate furniture for a room.

    This service is responsible for:
    - Querying furniture catalog for room-appropriate items
    - Prioritizing essential vs optional furniture
    - Considering user preferences (style, budget)
    - Calculating total space requirements
    - Providing feng shui placement notes
    """

    # Essential furniture categories by room type
    ESSENTIAL_CATEGORIES: dict[str, list[str]] = {
        "bedroom": ["bed"],
        "living_room": ["sofa"],
        "office": ["desk", "chair"],
        "dining_room": ["dining_table"],
        "studio_apartment": ["sofa_bed", "compact_wardrobe"],
    }

    # Standard furniture categories by room type
    STANDARD_CATEGORIES: dict[str, list[str]] = {
        "bedroom": ["bed", "nightstand", "wardrobe", "dresser"],
        "living_room": ["sofa", "coffee_table", "tv_stand", "armchair", "bookshelf"],
        "office": ["desk", "chair", "bookshelf", "filing_cabinet"],
        "dining_room": ["dining_table", "dining_chair", "sideboard"],
        "studio_apartment": [
            "sofa_bed",
            "compact_wardrobe",
            "folding_desk",
            "compact_dining",
            "shoe_cabinet",
            "room_divider",
        ],
    }

    # Feng shui placement notes by category
    FENG_SHUI_NOTES: dict[str, list[str]] = {
        "bed": [
            "Place in command position with headboard against solid wall",
            "Avoid placing directly in line with door",
            "Ensure you can see the door from the bed",
        ],
        "desk": [
            "Face the door while seated (command position)",
            "Solid wall behind for support",
            "Avoid sitting with back to door or window",
        ],
        "sofa": [
            "Place against a solid wall for support",
            "Face the main entry point",
            "Avoid placing under beams",
        ],
        "dining_table": [
            "Center of the dining area for family harmony",
            "Avoid placing in direct line with the door",
            "Ensure good lighting",
        ],
        "sofa_bed": [
            "Place against solid wall for stability",
            "Allow clear path when converting to bed",
            "Face the main entry point when in sofa mode",
        ],
        "folding_desk": [
            "Position in well-lit area near natural light",
            "Face the door while working (command position)",
            "Keep wall behind clear for folding mechanism",
        ],
        "room_divider": [
            "Use to separate sleep and living zones",
            "Ensure chi flow is not completely blocked",
            "Position to create privacy without closing off energy",
        ],
    }

    # Budget level mapping
    BUDGET_MAPPING: dict[str, BudgetLevel] = {
        "low": BudgetLevel.LOW,
        "medium": BudgetLevel.MEDIUM,
        "high": BudgetLevel.HIGH,
    }

    def __init__(self, furniture_tool: InMemoryFurnitureDbTool) -> None:
        """Initialize furniture selector.

        Args:
            furniture_tool: Tool for querying furniture database.
        """
        self.furniture_tool = furniture_tool

    async def select_furniture(
        self,
        room_type: str,
        usable_area: float,
        preferences: UserPreferences | None = None,
        max_items: int = 10,
        owned_categories: list[str] | None = None,
    ) -> FurnitureSelectionResult:
        """Select appropriate furniture for a room.

        Args:
            room_type: Type of room (bedroom, living_room, etc.).
            usable_area: Available floor area in square meters.
            preferences: User preferences for selection.
            max_items: Maximum number of items to select.
            owned_categories: If provided, restrict selection to only these
                categories (user explicitly stated what they own).

        Returns:
            FurnitureSelectionResult with selected items.
        """
        result = FurnitureSelectionResult()
        preferences = preferences or UserPreferences()

        if owned_categories:
            # User told us exactly what they have — use only those
            categories = owned_categories
            essential_categories = owned_categories  # treat all as essential
        else:
            # Get categories for this room type
            categories = self.STANDARD_CATEGORIES.get(room_type, [])
            essential_categories = self.ESSENTIAL_CATEGORIES.get(room_type, [])

        if not categories:
            result.warnings.append(f"Unknown room type: {room_type}")
            return result

        # Map budget level
        budget_level = self.BUDGET_MAPPING.get(preferences.budget_level, BudgetLevel.MEDIUM)

        # Query furniture for each category
        selected_area = 0.0
        priority = 1

        for category_str in categories:
            if len(result.selections) >= max_items:
                break

            # Convert string to FurnitureCategory
            try:
                category = FurnitureCategory(category_str)
            except ValueError:
                result.warnings.append(f"Unknown category: {category_str}")
                continue

            # Query furniture catalog.
            # When owned_categories is set the user may own furniture from a
            # different room type (e.g. a "desk" in a "bedroom"), so we search
            # the full catalog by category instead of filtering by room_type.
            if owned_categories:
                raw_items = [f for f in FURNITURE_CATALOG if f.category.value == category_str]
                items = [FurnitureSearchResult.from_catalog(f) for f in raw_items]
                if not items:
                    result.warnings.append(f"No {category_str} found in catalog")
                    continue
            else:
                query_result = await self.furniture_tool.execute(
                    FurnitureSearchInput(
                        room_type=room_type,
                        categories=[category],
                        budget_level=budget_level,
                    )
                )

                if not query_result.success or not query_result.data:
                    result.warnings.append(f"No {category_str} found for {room_type}")
                    continue

                items = query_result.data.results
                if not items:
                    result.warnings.append(f"No {category_str} items available")
                    continue

            # Select the best item for this category
            item = self._select_best_item(items, preferences, usable_area - selected_area)

            if item is None:
                result.skipped_items.append(category_str)
                result.warnings.append(f"No suitable {category_str} fits remaining space")
                continue

            # Calculate item area (including clearance)
            item_area = item.total_footprint

            # Check if it fits
            if selected_area + item_area > usable_area * 0.7:  # Max 70% of usable area
                if category_str in essential_categories:
                    result.warnings.append(
                        f"Essential {category_str} may be tight in available space"
                    )
                else:
                    result.skipped_items.append(category_str)
                    continue

            # Get feng shui notes
            feng_shui_notes = self.FENG_SHUI_NOTES.get(category_str, [])

            # Get alternatives
            alternatives = [i.id for i in items[1:4] if i.id != item.id]

            # Add selection
            selection = FurnitureSelection(
                item=item,
                priority=priority,
                is_essential=category_str in essential_categories,
                feng_shui_notes=feng_shui_notes,
                alternative_ids=alternatives,
            )

            result.selections.append(selection)
            selected_area += item_area
            priority += 1

        result.total_area_needed = selected_area
        return result

    def _select_best_item(
        self,
        items: list[FurnitureSearchResult],
        preferences: UserPreferences,
        available_area: float,
    ) -> FurnitureSearchResult | None:
        """Select the best item from available options.

        Args:
            items: Available furniture items.
            preferences: User preferences.
            available_area: Available floor area.

        Returns:
            Best matching item or None.
        """
        # Filter by size
        fitting_items = [item for item in items if item.total_footprint <= available_area]

        if not fitting_items:
            return None

        # Score items based on preferences
        scored_items = []
        for item in fitting_items:
            score = self._score_item(item, preferences)
            scored_items.append((score, item))

        # Sort by score (highest first)
        scored_items.sort(key=lambda x: x[0], reverse=True)
        return scored_items[0][1]

    def _score_item(self, item: FurnitureSearchResult, preferences: UserPreferences) -> float:
        """Score an item based on preferences.

        Args:
            item: Furniture item to score.
            preferences: User preferences.

        Returns:
            Score (higher is better).
        """
        score = 50.0  # Base score

        # Budget match (item.budget_level is a string)
        preferred_budget = preferences.budget_level
        budget_order = ["low", "medium", "high"]

        if item.budget_level == preferred_budget:
            score += 20
        else:
            # Give partial score for close budgets
            try:
                item_idx = budget_order.index(item.budget_level)
                pref_idx = budget_order.index(preferred_budget)
                if abs(item_idx - pref_idx) == 1:
                    score += 10
            except ValueError:
                pass  # Unknown budget level

        # Essential items get bonus
        if item.is_essential:
            score += 15

        # Feng shui element bonus
        if item.feng_shui_element:
            score += 5

        return score

    def update_context(
        self,
        context: AgentContext,
        result: FurnitureSelectionResult,
    ) -> None:
        """Update agent context with selection results.

        Args:
            context: Agent context to update.
            result: Selection result.
        """
        # Store selected furniture in context
        context.selected_furniture = [
            {
                "id": s.item.id,
                "furniture_id": s.item.id,
                "name": s.item.name,
                "category": s.item.category,
                "width": s.item.width,
                "depth": s.item.depth,
                "height": s.item.height,
                "is_essential": s.is_essential,
                "priority": s.priority,
            }
            for s in result.get_by_priority()
        ]

        # Store metadata
        context.metadata["furniture_selection"] = {
            "total_items": len(result.selections),
            "essential_items": result.essential_count,
            "optional_items": result.optional_count,
            "total_area_needed": result.total_area_needed,
            "warnings": result.warnings,
            "skipped_items": result.skipped_items,
        }

    def select_essential_only(
        self,
        room_type: str,
        items: list[FurnitureSearchResult],
    ) -> list[FurnitureSelection]:
        """Select only essential furniture from given items.

        Args:
            room_type: Type of room.
            items: Available furniture items.

        Returns:
            List of essential furniture selections.
        """
        essential_categories = self.ESSENTIAL_CATEGORIES.get(room_type, [])
        selections = []
        priority = 1

        for category in essential_categories:
            category_items = [i for i in items if i.category == category]
            if category_items:
                item = category_items[0]  # Select first matching item
                feng_shui_notes = self.FENG_SHUI_NOTES.get(category, [])
                selections.append(
                    FurnitureSelection(
                        item=item,
                        priority=priority,
                        is_essential=True,
                        feng_shui_notes=feng_shui_notes,
                    )
                )
                priority += 1

        return selections

    def get_furniture_for_zone(
        self,
        zone_type: str,
        room_type: str,
    ) -> list[str]:
        """Get appropriate furniture categories for a zone.

        Args:
            zone_type: Type of zone (work, rest, etc.).
            room_type: Type of room.

        Returns:
            List of furniture categories suitable for the zone.
        """
        zone_furniture_map = {
            "work": ["desk", "chair", "bookshelf"],
            "rest": ["bed", "nightstand", "dresser"],
            "natural_light": ["desk", "reading_chair", "plants"],
            "traffic": [],  # Don't place furniture in traffic zones
        }

        zone_categories = zone_furniture_map.get(zone_type, [])
        room_categories = self.STANDARD_CATEGORIES.get(room_type, [])

        # Return intersection of zone and room furniture
        return [c for c in zone_categories if c in room_categories]
