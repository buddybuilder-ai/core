"""RAG search tool for feng shui layout agent."""

from abc import abstractmethod
from dataclasses import dataclass, field
from typing import Any

from src.modules.layout.infrastructure.tools.base import BaseTool, ToolResult
from src.modules.layout.infrastructure.tools.feng_shui_rules_data import (
    FENG_SHUI_RULES,
    FengShuiRule,
    RuleCategory,
    get_rules_by_category,
    get_rules_for_furniture,
    get_rules_for_room_type,
    search_rules_by_keywords,
)


@dataclass(frozen=True)
class RagSearchInput:
    """Input for RAG search.

    Attributes:
        query: Free-text query to search for.
        room_type: Optional room type to filter by.
        furniture_types: Optional furniture types to filter by.
        categories: Optional categories to filter by.
        max_results: Maximum number of results to return.
    """

    query: str
    room_type: str | None = None
    furniture_types: list[str] = field(default_factory=list)
    categories: list[RuleCategory] = field(default_factory=list)
    max_results: int = 5


@dataclass(frozen=True)
class RuleSearchResult:
    """A single search result.

    Attributes:
        rule_id: ID of the matched rule.
        title: Title of the rule.
        description: Description of the rule.
        category: Category of the rule.
        priority: Priority weight.
        relevance_score: Relevance score (higher = more relevant).
        applicable_furniture: Furniture types this rule applies to.
    """

    rule_id: str
    title: str
    description: str
    category: str
    priority: int
    relevance_score: float
    applicable_furniture: list[str]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "rule_id": self.rule_id,
            "title": self.title,
            "description": self.description,
            "category": self.category,
            "priority": self.priority,
            "relevance_score": self.relevance_score,
            "applicable_furniture": self.applicable_furniture,
        }


@dataclass(frozen=True)
class RagSearchOutput:
    """Output of RAG search.

    Attributes:
        results: List of search results.
        total_matches: Total number of matches found.
        query_processed: The processed query string.
    """

    results: list[RuleSearchResult]
    total_matches: int
    query_processed: str

    @property
    def has_results(self) -> bool:
        """Check if any results were found."""
        return len(self.results) > 0

    def get_top_result(self) -> RuleSearchResult | None:
        """Get the most relevant result."""
        return self.results[0] if self.results else None

    def get_results_by_category(self, category: str) -> list[RuleSearchResult]:
        """Get results in a specific category."""
        return [r for r in self.results if r.category == category]


class BaseRagSearchTool(BaseTool[RagSearchInput, RagSearchOutput]):
    """Abstract base class for RAG search tools.

    This provides an interface that can be implemented with different backends:
    - MockRagSearchTool: Uses hardcoded feng shui rules
    - ChromaDbRagSearchTool: Uses ChromaDB for vector search (future)
    """

    @property
    def name(self) -> str:
        return "RAG_SEARCH"

    @property
    def description(self) -> str:
        return (
            "Searches feng shui knowledge base for relevant rules and guidelines. "
            "Returns rules for room layout, furniture placement, command position, "
            "five elements balance, chi flow, and sha chi avoidance."
        )

    def validate_input(self, input_data: RagSearchInput) -> list[str]:
        """Validate search input."""
        errors = []
        if not input_data.query or not input_data.query.strip():
            errors.append("Query cannot be empty")
        if input_data.max_results < 1:
            errors.append("max_results must be at least 1")
        if input_data.max_results > 50:
            errors.append("max_results cannot exceed 50")
        return errors

    @abstractmethod
    async def execute(self, input_data: RagSearchInput) -> ToolResult[RagSearchOutput]:
        """Execute the search. Must be implemented by subclasses."""
        ...

    def to_langchain_tool_schema(self) -> dict[str, Any]:
        """Convert to LangChain tool schema."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Free-text query for feng shui rules",
                    },
                    "room_type": {
                        "type": "string",
                        "enum": ["bedroom", "living_room", "office", "dining_room"],
                        "description": "Room type to filter results",
                    },
                    "furniture_types": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Furniture types to filter results",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum results to return (default 5)",
                    },
                },
                "required": ["query"],
            },
        }


class MockRagSearchTool(BaseRagSearchTool):
    """Mock RAG search tool using hardcoded feng shui rules.

    This implementation uses keyword matching and filtering against
    a hardcoded knowledge base. It can be replaced with a real vector
    database implementation (e.g., ChromaDB) in the future.
    """

    def __init__(self) -> None:
        """Initialize the mock RAG search tool."""
        self._rules = FENG_SHUI_RULES

    async def execute(self, input_data: RagSearchInput) -> ToolResult[RagSearchOutput]:
        """Execute search against hardcoded rules."""
        import time

        start_time = time.perf_counter()

        # Parse query into keywords
        query = input_data.query.lower().strip()
        keywords = [w for w in query.split() if len(w) > 2]

        # Start with keyword search
        if keywords:
            keyword_results = search_rules_by_keywords(keywords)
            matched_rules = [r[0] for r in keyword_results]
        else:
            matched_rules = list(self._rules)

        # Apply filters
        if input_data.room_type:
            room_rules = {r.id for r in get_rules_for_room_type(input_data.room_type)}
            matched_rules = [r for r in matched_rules if r.id in room_rules]

        if input_data.furniture_types:
            furniture_rule_ids: set[str] = set()
            for furniture_type in input_data.furniture_types:
                for rule in get_rules_for_furniture(furniture_type):
                    furniture_rule_ids.add(rule.id)
            if furniture_rule_ids:
                matched_rules = [r for r in matched_rules if r.id in furniture_rule_ids]

        if input_data.categories:
            category_rule_ids: set[str] = set()
            for category in input_data.categories:
                for rule in get_rules_by_category(category):
                    category_rule_ids.add(rule.id)
            if category_rule_ids:
                matched_rules = [r for r in matched_rules if r.id in category_rule_ids]

        # Calculate relevance scores
        scored_rules: list[tuple[FengShuiRule, float]] = []
        for rule in matched_rules:
            score = self._calculate_relevance(rule, keywords, input_data)
            scored_rules.append((rule, score))

        # Sort by relevance score
        scored_rules.sort(key=lambda x: (x[1], x[0].priority), reverse=True)

        # Limit results
        total_matches = len(scored_rules)
        scored_rules = scored_rules[: input_data.max_results]

        # Convert to output format
        results = [
            RuleSearchResult(
                rule_id=rule.id,
                title=rule.title,
                description=rule.description,
                category=rule.category.value,
                priority=rule.priority,
                relevance_score=score,
                applicable_furniture=list(rule.furniture_types),
            )
            for rule, score in scored_rules
        ]

        elapsed_ms = (time.perf_counter() - start_time) * 1000

        output = RagSearchOutput(
            results=results,
            total_matches=total_matches,
            query_processed=query,
        )

        return ToolResult.ok(
            data=output,
            execution_time_ms=elapsed_ms,
            metadata={
                "query": query,
                "keywords": keywords,
                "filters_applied": {
                    "room_type": input_data.room_type,
                    "furniture_types": input_data.furniture_types,
                    "categories": [c.value for c in input_data.categories],
                },
                "total_matches": total_matches,
                "results_returned": len(results),
            },
        )

    def _calculate_relevance(
        self,
        rule: FengShuiRule,
        keywords: list[str],
        input_data: RagSearchInput,
    ) -> float:
        """Calculate relevance score for a rule.

        Args:
            rule: The rule to score.
            keywords: Query keywords.
            input_data: Original search input.

        Returns:
            Relevance score between 0 and 1.
        """
        score = 0.0

        # Base score from priority (normalized to 0-0.3)
        score += (rule.priority / 100) * 0.3

        # Keyword matches (up to 0.4)
        if keywords:
            rule_text = (
                rule.title.lower() + " " + rule.description.lower() + " " + " ".join(rule.keywords)
            )
            matches = sum(1 for k in keywords if k in rule_text)
            keyword_score = min(matches / len(keywords), 1.0) * 0.4
            score += keyword_score

        # Room type match (0.15)
        if input_data.room_type and input_data.room_type in rule.room_types:
            score += 0.15

        # Furniture match (0.15)
        if input_data.furniture_types:
            furniture_matches = sum(
                1 for f in input_data.furniture_types if f in rule.furniture_types
            )
            if furniture_matches > 0:
                score += 0.15 * (furniture_matches / len(input_data.furniture_types))

        return min(score, 1.0)

    def get_all_rules(self) -> list[FengShuiRule]:
        """Get all rules in the knowledge base (for testing)."""
        return list(self._rules)

    def get_rule_by_id(self, rule_id: str) -> FengShuiRule | None:
        """Get a specific rule by ID (for testing)."""
        for rule in self._rules:
            if rule.id == rule_id:
                return rule
        return None
