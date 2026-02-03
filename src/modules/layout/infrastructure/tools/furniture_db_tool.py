"""Furniture database tool for feng shui layout agent."""

from dataclasses import dataclass, field
from typing import Any

from src.modules.layout.infrastructure.tools.base import BaseTool, ToolResult
from src.modules.layout.infrastructure.tools.furniture_catalog_data import (
    FURNITURE_CATALOG,
    BudgetLevel,
    CatalogFurniture,
    FurnitureCategory,
    get_essential_furniture,
    get_furniture_by_budget,
    get_furniture_by_category,
    get_furniture_by_id,
    get_furniture_by_room_type,
)


@dataclass(frozen=True)
class FurnitureSearchInput:
    """Input for furniture search.

    Attributes:
        room_type: Room type to search for.
        categories: Optional furniture categories to filter by.
        budget_level: Optional budget level to filter by.
        essential_only: Only return essential furniture.
        max_results: Maximum results to return.
        min_width: Minimum width in meters.
        max_width: Maximum width in meters.
        min_depth: Minimum depth in meters.
        max_depth: Maximum depth in meters.
    """

    room_type: str
    categories: list[FurnitureCategory] = field(default_factory=list)
    budget_level: BudgetLevel | None = None
    essential_only: bool = False
    max_results: int = 20
    min_width: float | None = None
    max_width: float | None = None
    min_depth: float | None = None
    max_depth: float | None = None


@dataclass(frozen=True)
class FurnitureSearchResult:
    """A furniture item search result.

    Attributes:
        id: Furniture ID.
        name: Display name.
        category: Furniture category.
        width: Width in meters.
        depth: Depth in meters.
        height: Height in meters.
        budget_level: Budget level.
        is_essential: Whether essential for room.
        clearance_front: Required front clearance.
        clearance_sides: Required side clearance.
        feng_shui_element: Associated feng shui element.
        placement_notes: Placement recommendations.
        total_footprint: Total space needed including clearance.
    """

    id: str
    name: str
    category: str
    width: float
    depth: float
    height: float
    budget_level: str
    is_essential: bool
    clearance_front: float
    clearance_sides: float
    feng_shui_element: str
    placement_notes: str
    total_footprint: float

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "width": self.width,
            "depth": self.depth,
            "height": self.height,
            "budget_level": self.budget_level,
            "is_essential": self.is_essential,
            "clearance_front": self.clearance_front,
            "clearance_sides": self.clearance_sides,
            "feng_shui_element": self.feng_shui_element,
            "placement_notes": self.placement_notes,
            "total_footprint": self.total_footprint,
        }

    @classmethod
    def from_catalog(cls, furniture: CatalogFurniture) -> "FurnitureSearchResult":
        """Create from catalog furniture."""
        return cls(
            id=furniture.id,
            name=furniture.name,
            category=furniture.category.value,
            width=furniture.width,
            depth=furniture.depth,
            height=furniture.height,
            budget_level=furniture.budget_level.value,
            is_essential=furniture.is_essential,
            clearance_front=furniture.clearance_front,
            clearance_sides=furniture.clearance_sides,
            feng_shui_element=furniture.feng_shui_element,
            placement_notes=furniture.placement_notes,
            total_footprint=furniture.total_footprint,
        )


@dataclass(frozen=True)
class FurnitureSearchOutput:
    """Output of furniture search.

    Attributes:
        results: List of matching furniture.
        total_matches: Total matches before limiting.
        essential_count: Number of essential items in results.
        categories_found: Categories present in results.
    """

    results: list[FurnitureSearchResult]
    total_matches: int
    essential_count: int
    categories_found: list[str]

    @property
    def has_results(self) -> bool:
        """Check if any results were found."""
        return len(self.results) > 0

    def get_by_category(self, category: str) -> list[FurnitureSearchResult]:
        """Get results in a specific category."""
        return [r for r in self.results if r.category == category]

    def get_essential_items(self) -> list[FurnitureSearchResult]:
        """Get only essential items."""
        return [r for r in self.results if r.is_essential]


class InMemoryFurnitureDbTool(BaseTool[FurnitureSearchInput, FurnitureSearchOutput]):
    """In-memory furniture database tool.

    This implementation uses a hardcoded furniture catalog.
    It can be replaced with a real database implementation later.
    """

    def __init__(self) -> None:
        """Initialize with furniture catalog."""
        self._catalog = FURNITURE_CATALOG

    @property
    def name(self) -> str:
        return "FURNITURE_DB"

    @property
    def description(self) -> str:
        return (
            "Searches furniture catalog for items suitable for a room. "
            "Returns furniture with dimensions, clearance requirements, "
            "feng shui elements, and placement recommendations."
        )

    def validate_input(self, input_data: FurnitureSearchInput) -> list[str]:
        """Validate search input."""
        errors = []
        valid_room_types = {"bedroom", "living_room", "office", "dining_room"}
        if input_data.room_type not in valid_room_types:
            errors.append(f"Invalid room_type. Must be one of: {valid_room_types}")
        if input_data.max_results < 1:
            errors.append("max_results must be at least 1")
        if input_data.min_width is not None and input_data.min_width < 0:
            errors.append("min_width must be non-negative")
        if input_data.max_width is not None and input_data.max_width < 0:
            errors.append("max_width must be non-negative")
        if input_data.min_depth is not None and input_data.min_depth < 0:
            errors.append("min_depth must be non-negative")
        if input_data.max_depth is not None and input_data.max_depth < 0:
            errors.append("max_depth must be non-negative")
        return errors

    async def execute(self, input_data: FurnitureSearchInput) -> ToolResult[FurnitureSearchOutput]:
        """Execute furniture search."""
        import time

        start_time = time.perf_counter()

        # Start with room type filter
        results = get_furniture_by_room_type(input_data.room_type)

        # Apply category filter
        if input_data.categories:
            category_values = {c.value for c in input_data.categories}
            results = [f for f in results if f.category.value in category_values]

        # Apply budget filter
        if input_data.budget_level is not None:
            results = [f for f in results if f.budget_level == input_data.budget_level]

        # Apply essential filter
        if input_data.essential_only:
            results = [f for f in results if f.is_essential]

        # Apply dimension filters
        if input_data.min_width is not None:
            results = [f for f in results if f.width >= input_data.min_width]
        if input_data.max_width is not None:
            results = [f for f in results if f.width <= input_data.max_width]
        if input_data.min_depth is not None:
            results = [f for f in results if f.depth >= input_data.min_depth]
        if input_data.max_depth is not None:
            results = [f for f in results if f.depth <= input_data.max_depth]

        # Calculate statistics before limiting
        total_matches = len(results)
        essential_count = sum(1 for f in results if f.is_essential)
        categories_found = list({f.category.value for f in results})

        # Sort: essential first, then by category
        results.sort(key=lambda f: (not f.is_essential, f.category.value, f.name))

        # Limit results
        results = results[: input_data.max_results]

        # Convert to output format
        search_results = [FurnitureSearchResult.from_catalog(f) for f in results]

        elapsed_ms = (time.perf_counter() - start_time) * 1000

        output = FurnitureSearchOutput(
            results=search_results,
            total_matches=total_matches,
            essential_count=essential_count,
            categories_found=categories_found,
        )

        return ToolResult.ok(
            data=output,
            execution_time_ms=elapsed_ms,
            metadata={
                "room_type": input_data.room_type,
                "total_matches": total_matches,
                "results_returned": len(search_results),
                "essential_count": essential_count,
            },
        )

    def get_furniture_by_id(self, furniture_id: str) -> CatalogFurniture | None:
        """Get a specific furniture item by ID."""
        return get_furniture_by_id(furniture_id)

    def get_all_categories(self) -> list[str]:
        """Get all available furniture categories."""
        return [c.value for c in FurnitureCategory]

    def get_catalog_size(self) -> int:
        """Get the size of the furniture catalog."""
        return len(self._catalog)

    def to_langchain_tool_schema(self) -> dict[str, Any]:
        """Convert to LangChain tool schema."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "room_type": {
                        "type": "string",
                        "enum": ["bedroom", "living_room", "office", "dining_room"],
                        "description": "Type of room to search furniture for",
                    },
                    "categories": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": [c.value for c in FurnitureCategory],
                        },
                        "description": "Furniture categories to filter by",
                    },
                    "budget_level": {
                        "type": "string",
                        "enum": ["low", "medium", "high"],
                        "description": "Budget level filter",
                    },
                    "essential_only": {
                        "type": "boolean",
                        "description": "Only return essential furniture",
                    },
                },
                "required": ["room_type"],
            },
        }
