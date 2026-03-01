"""RAG Context Injector — retrieves relevant feng shui knowledge for a pipeline run.

Called between Step 1 (DataBuilder) and Step 2 (LayoutGenerator) by the
PipelineOrchestrator.  Stores results in PipelineState.rag_context for use by:
  - Step 2: injects rule text into the LLM plan_layout() prompt
  - Step 3: enriches Conflict.suggestion with rule descriptions
  - /chat/stream question path: augments Q&A answers

Graceful degradation: all errors are caught; an empty RagContext is returned
so the pipeline continues unmodified.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from src.modules.layout.infrastructure.tools.rag_search_tool import (
    BaseRagSearchTool,
    MockRagSearchTool,
    RagSearchInput,
    RuleSearchResult,
)

logger = logging.getLogger(__name__)

# Maximum rules to include in the LLM prompt (token budget)
_MAX_RULES_IN_PROMPT = 6


@dataclass
class RagContext:
    """Holds retrieved RAG data for one pipeline run.

    Attributes:
        rules: Raw search results from the knowledge base.
        layout_prompt_context: Formatted text for Step 2's LLM prompt.
        rule_descriptions: rule_id → description dict for Step 3 suggestion enrichment.
        source_citations: Human-readable rule titles for Q&A citations.
    """

    rules: list[RuleSearchResult] = field(default_factory=list)
    layout_prompt_context: str = ""
    rule_descriptions: dict[str, str] = field(default_factory=dict)
    source_citations: list[str] = field(default_factory=list)


class ContextInjector:
    """Retrieves relevant feng shui context for a room spec.

    Uses MockRagSearchTool by default (keyword-based, always available).
    Can be constructed with a ChromaDbRagSearchTool for vector-based retrieval.

    Usage:
        injector = ContextInjector()
        ctx = await injector.retrieve(state.room_spec)
        # ctx.layout_prompt_context → str to pass as extra_context to plan_layout()
        # ctx.rule_descriptions     → dict for Step 3 conflict enrichment
    """

    def __init__(self, rag_tool: BaseRagSearchTool | None = None) -> None:
        self._tool = rag_tool or MockRagSearchTool()

    async def retrieve(self, room_spec: dict[str, Any]) -> RagContext:
        """Build queries from room_spec, retrieve top rules, format context.

        Always returns a valid RagContext.  Never raises.

        Args:
            room_spec: The pipeline's room_spec dict.  Reads room_type and
                       user_preferences.concern if present.

        Returns:
            RagContext with formatted context strings and rule lookup dicts.
        """
        try:
            queries = self._build_queries(room_spec)
            all_results = await self._run_queries(queries)
            deduped = self._deduplicate(all_results)

            logger.info(
                f"🔍 ContextInjector: retrieved {len(deduped)} unique rules "
                f"for room_type={room_spec.get('room_type', '?')!r}"
            )

            return RagContext(
                rules=deduped,
                layout_prompt_context=self._format_layout_context(deduped),
                rule_descriptions={r.rule_id: r.description for r in deduped},
                source_citations=[f"[{r.category}] {r.title}" for r in deduped],
            )

        except Exception as exc:
            logger.warning(f"ContextInjector.retrieve() failed (continuing): {exc}")
            return RagContext()

    # ------------------------------------------------------------------
    # Query construction
    # ------------------------------------------------------------------

    def _build_queries(self, room_spec: dict[str, Any]) -> list[RagSearchInput]:
        """Build 2–3 search queries from room spec context."""
        room_type = room_spec.get("room_type", "")
        user_prefs = room_spec.get("user_preferences", {}) or {}
        concern = str(user_prefs.get("concern", ""))

        queries: list[RagSearchInput] = []

        # Primary: general room-type query
        if room_type:
            queries.append(
                RagSearchInput(
                    query=f"feng shui {room_type} furniture placement",
                    room_type=room_type,
                    max_results=5,
                )
            )

        # Secondary: command position (always relevant)
        queries.append(
            RagSearchInput(
                query="command position furniture placement",
                room_type=room_type or None,
                max_results=3,
            )
        )

        # Optional: user concern (e.g. "wealth", "health", "sleep")
        if concern and room_type:
            queries.append(
                RagSearchInput(
                    query=f"feng shui {concern} {room_type}",
                    room_type=room_type,
                    max_results=3,
                )
            )
        elif concern:
            queries.append(
                RagSearchInput(
                    query=f"feng shui {concern}",
                    max_results=3,
                )
            )

        return queries

    async def _run_queries(
        self, queries: list[RagSearchInput]
    ) -> list[RuleSearchResult]:
        """Execute all queries, collect results. Ignores individual query errors."""
        results: list[RuleSearchResult] = []
        for q in queries:
            try:
                tool_result = await self._tool.execute(q)
                if tool_result.success and tool_result.data:
                    results.extend(tool_result.data.results)
            except Exception as exc:
                logger.debug(f"ContextInjector query failed ({q.query!r}): {exc}")
        return results

    @staticmethod
    def _deduplicate(results: list[RuleSearchResult]) -> list[RuleSearchResult]:
        """Remove duplicate rule_ids, keeping highest relevance_score."""
        seen: dict[str, RuleSearchResult] = {}
        for r in results:
            if r.rule_id not in seen or r.relevance_score > seen[r.rule_id].relevance_score:
                seen[r.rule_id] = r
        return sorted(seen.values(), key=lambda r: r.relevance_score, reverse=True)

    # ------------------------------------------------------------------
    # Formatting
    # ------------------------------------------------------------------

    @staticmethod
    def _format_layout_context(results: list[RuleSearchResult]) -> str:
        """Format top rules as a bulleted list for the LLM prompt.

        Caps at _MAX_RULES_IN_PROMPT to stay within token budget.
        Returns empty string if no results.
        """
        if not results:
            return ""
        lines = ["## Relevant Feng Shui Rules (from knowledge base):"]
        for r in results[:_MAX_RULES_IN_PROMPT]:
            lines.append(f"- [{r.category}] {r.title}: {r.description}")
        return "\n".join(lines)
