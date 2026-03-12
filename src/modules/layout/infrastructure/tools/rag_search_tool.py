"""RAG search tool for feng shui layout agent.

Two concrete implementations are provided:

* ``MockRagSearchTool``  – keyword-matching against a hardcoded rules list.
  Zero external dependencies; ideal for unit tests.

* ``ChromaDbRagSearchTool`` – semantic vector search against the real
  ChromaDB vectorstore that was built by the feng-shui-rag indexing pipeline.
  Requires ``sentence-transformers`` / ``langchain-community`` to be installed.
"""

from __future__ import annotations

import logging
from abc import abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

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

if TYPE_CHECKING:
    from langchain_community.vectorstores import Chroma

logger = logging.getLogger(__name__)


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


class ChromaDbRagSearchTool(BaseRagSearchTool):
    """Real RAG search tool backed by a local ChromaDB vectorstore.

    This implementation performs semantic vector search against the ChromaDB
    database that was built by the feng-shui-rag indexing pipeline
    (``feng-shui-rag/src/step3_vectorstore.py``).

    Results from ChromaDB are LangChain ``Document`` objects; this class
    converts them into the same ``RuleSearchResult`` / ``RagSearchOutput``
    shape that ``MockRagSearchTool`` produces, so the rest of the agent code
    is completely unaware of which backend is in use.

    Args:
        db_path: Path to the ChromaDB persistence directory.
            Defaults to the value in ``Settings.CHROMA_DB_PATH``.
        embedding_model: HuggingFace model identifier used when the store was
            built.  Defaults to ``Settings.EMBEDDING_MODEL_LOCAL``.
        top_k: Number of documents to retrieve per query.
            Defaults to ``Settings.RAG_TOP_K``.
        search_type: Retrieval mode – ``'mmr'`` or ``'similarity'``.
            Defaults to ``Settings.RAG_SEARCH_TYPE``.
        relevance_threshold: L2-distance cut-off; queries whose best match
            exceeds this value are treated as out-of-scope.
            Defaults to ``Settings.RAG_RELEVANCE_THRESHOLD``.
    """

    def __init__(
        self,
        db_path: str | None = None,
        embedding_model: str | None = None,
        top_k: int | None = None,
        search_type: str | None = None,
        relevance_threshold: float | None = None,
    ) -> None:
        from src.config.settings import get_settings

        settings = get_settings()

        self._db_path = db_path or settings.CHROMA_DB_PATH
        self._embedding_model = embedding_model or settings.EMBEDDING_MODEL_LOCAL
        self._top_k = top_k if top_k is not None else settings.RAG_TOP_K
        self._search_type = search_type or settings.RAG_SEARCH_TYPE
        self._relevance_threshold = (
            relevance_threshold
            if relevance_threshold is not None
            else settings.RAG_RELEVANCE_THRESHOLD
        )

        # Lazy-loaded vectorstore (initialised on first execute call)
        self._vectorstore: Chroma | None = None

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _ensure_vectorstore(self) -> "Chroma":
        """Load the vectorstore on first use (lazy initialisation)."""
        if self._vectorstore is None:
            from src.modules.layout.infrastructure.vectorstore_service import (
                get_cached_vectorstore,
            )

            self._vectorstore = get_cached_vectorstore(
                self._db_path, self._embedding_model
            )
        return self._vectorstore

    def _is_in_scope(self, query: str) -> bool:
        """Return True if the query's best L2 distance is below the threshold."""
        try:
            vs = self._ensure_vectorstore()
            results = vs.similarity_search_with_score(query, k=1)
            if not results:
                return False
            best_score = results[0][1]
            logger.debug(
                "RAG relevance check: query=%r score=%.3f threshold=%.3f",
                query,
                best_score,
                self._relevance_threshold,
            )
            return bool(best_score <= self._relevance_threshold)
        except Exception as exc:
            logger.warning("RAG relevance check failed (%s) — allowing query", exc)
            return True

    @staticmethod
    def _doc_to_result(doc: "object", score: float, index: int) -> RuleSearchResult:
        """Convert a LangChain Document to a RuleSearchResult.

        Because ChromaDB documents come from raw text chunks (not structured
        rules), we synthesise a lightweight result using the document metadata
        and content excerpt.
        """
        from langchain_core.documents import Document as LCDocument

        assert isinstance(doc, LCDocument)

        metadata = doc.metadata or {}
        source = str(metadata.get("source", "vectorstore"))

        # Derive a short title from the first non-empty line of the chunk
        first_line = next(
            (line.strip() for line in doc.page_content.splitlines() if line.strip()),
            "Feng Shui Knowledge",
        )
        title = first_line[:80]

        # Normalise the L2 distance to a 0-1 relevance score
        # L2 range: 0 (identical) → ~1.4 (orthogonal for normalised embeddings)
        relevance = max(0.0, 1.0 - score / 1.4)

        # Infer category from metadata or source filename
        category = str(
            metadata.get(
                "category",
                metadata.get(
                    "topic_th",
                    _infer_category_from_source(source),
                ),
            )
        )

        return RuleSearchResult(
            rule_id=f"chroma_{index:04d}",
            title=title,
            description=doc.page_content.strip()[:500],
            category=category,
            priority=max(1, int(round(relevance * 100))),
            relevance_score=round(relevance, 4),
            applicable_furniture=_extract_furniture_hints(doc.page_content),
        )

    # ------------------------------------------------------------------
    # BaseTool interface
    # ------------------------------------------------------------------

    async def execute(self, input_data: RagSearchInput) -> ToolResult[RagSearchOutput]:
        """Perform vector similarity search against the ChromaDB vectorstore."""
        import time

        start_time = time.perf_counter()
        query = input_data.query.strip()

        # Out-of-scope guard (mirrors feng-shui-rag relevance check)
        if not self._is_in_scope(query):
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            output = RagSearchOutput(
                results=[],
                total_matches=0,
                query_processed=query,
            )
            return ToolResult.ok(
                data=output,
                execution_time_ms=elapsed_ms,
                metadata={"reason": "out_of_scope", "query": query},
            )

        try:
            vs = self._ensure_vectorstore()

            # Build optional metadata filter
            where_filter: dict[str, Any] | None = None
            if input_data.room_type:
                where_filter = {"topic_th": {"$contains": input_data.room_type}}

            # Retrieve documents with scores
            docs_with_scores = vs.similarity_search_with_score(
                query,
                k=input_data.max_results,
                filter=where_filter,
            )

            results = [
                self._doc_to_result(doc, score, i)
                for i, (doc, score) in enumerate(docs_with_scores)
            ]

            # Sort by relevance descending
            results.sort(key=lambda r: r.relevance_score, reverse=True)

            # Apply furniture filter if requested (post-retrieval)
            if input_data.furniture_types:
                ftypes_lower = {f.lower() for f in input_data.furniture_types}
                results = [
                    r
                    for r in results
                    if any(f in ftypes_lower for f in r.applicable_furniture)
                       or not r.applicable_furniture
                ]

            # Apply category filter if requested (post-retrieval)
            if input_data.categories:
                cat_values = {c.value for c in input_data.categories}
                results = [r for r in results if r.category in cat_values]

            total_matches = len(results)
            results = results[: input_data.max_results]

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
                    "db_path": self._db_path,
                    "embedding_model": self._embedding_model,
                    "total_matches": total_matches,
                    "results_returned": len(results),
                    "filters_applied": {
                        "room_type": input_data.room_type,
                        "furniture_types": input_data.furniture_types,
                        "categories": [c.value for c in input_data.categories],
                    },
                },
            )

        except Exception as exc:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            logger.exception("ChromaDbRagSearchTool execution failed")
            return ToolResult.fail(
                error=f"ChromaDB search failed: {exc}",
                execution_time_ms=elapsed_ms,
            )


# ---------------------------------------------------------------------------
# Module-level helper utilities
# ---------------------------------------------------------------------------

def _infer_category_from_source(source: str) -> str:
    """Guess a RuleCategory value from a source filename."""
    source_lower = source.lower()
    if any(k in source_lower for k in ("conflict", "rules", "rule")):
        return RuleCategory.FURNITURE_PLACEMENT.value
    if any(k in source_lower for k in ("direction", "direct")):
        return RuleCategory.ROOM_LAYOUT.value
    if any(k in source_lower for k in ("gua", "element")):
        return RuleCategory.FIVE_ELEMENTS.value
    return RuleCategory.ROOM_LAYOUT.value


def _extract_furniture_hints(text: str) -> list[str]:
    """Extract furniture type hints mentioned in a text chunk."""
    furniture_keywords = [
        "bed", "desk", "sofa", "wardrobe", "closet", "chair",
        "table", "nightstand", "mirror", "shelf", "bookshelf",
        "เตียง", "โต๊ะ", "ตู้", "เก้าอี้", "โซฟา", "ชั้น",
    ]
    text_lower = text.lower()
    return [kw for kw in furniture_keywords if kw in text_lower]
