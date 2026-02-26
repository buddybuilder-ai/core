"""Step 5: Explainer.

Summarizes the layout generation process:
- What was placed and why
- Conflicts found and how they were resolved
- Feng shui score breakdown and recommendations
- Remaining issues (if any)

Currently generates explanation via template.
LLM-powered natural language explanation can be added later.
"""

from __future__ import annotations

import logging
from typing import AsyncGenerator

from src.modules.layout.application.pipeline.models import (
    Conflict,
    ConflictSeverity,
    PipelineConfig,
    PipelineState,
    PipelineStep,
    RepairAction,
    SSEEvent,
)
from src.modules.layout.application.pipeline.steps.base import BaseStep

logger = logging.getLogger(__name__)

# Feng shui grade thresholds
GRADE_EXCELLENT = 80
GRADE_GOOD = 60
GRADE_FAIR = 40


class ExplainerStep(BaseStep):
    """Step 5: Generate explanation of layout decisions."""

    step = PipelineStep.EXPLAINER

    async def execute(
        self, state: PipelineState
    ) -> AsyncGenerator[SSEEvent, None]:
        yield self._emit_started()
        yield self._emit_progress("Generating explanation...", 0.3)

        explanation_parts: list[str] = []

        # --- Layout summary ---
        items = state.layout_items
        spec = state.room_spec
        room_type = spec.get("room_type", "room")
        width = spec.get("width", 0)
        depth = spec.get("depth", 0)

        explanation_parts.append(
            f"## Layout Summary\n"
            f"Generated layout for **{room_type}** ({width}m × {depth}m) "
            f"with **{len(items)} furniture items** placed."
        )

        # Categorize items
        categories: dict[str, list[str]] = {}
        for item in items:
            cat = item.get("category", "other")
            categories.setdefault(cat, []).append(item.get("name", ""))

        if categories:
            cat_lines = [f"- **{cat}**: {', '.join(names)}" for cat, names in categories.items()]
            explanation_parts.append("### Items Placed\n" + "\n".join(cat_lines))

        # --- Conflicts & Repairs ---
        yield self._emit_progress("Summarizing conflicts...", 0.5)

        all_conflicts = state.conflicts
        resolved = [c for c in all_conflicts if c.resolved]
        unresolved = state.unresolved_conflicts

        if all_conflicts:
            explanation_parts.append(
                f"## Conflicts\n"
                f"Found **{len(all_conflicts)} conflicts** total. "
                f"Resolved **{len(resolved)}**, "
                f"remaining **{len(unresolved)}**."
            )

            if resolved:
                repair_lines = self._summarize_repairs(state.repair_actions)
                explanation_parts.append("### Repairs Applied\n" + "\n".join(repair_lines))

            if unresolved:
                issue_lines = self._summarize_unresolved(unresolved)
                explanation_parts.append("### Remaining Issues\n" + "\n".join(issue_lines))
        else:
            explanation_parts.append("## Conflicts\nNo conflicts detected — clean layout!")

        # --- Feng Shui ---
        yield self._emit_progress("Feng shui analysis...", 0.8)

        score = state.feng_shui_score
        if score:
            total = sum(score.values())
            grade = self._get_grade(total)
            explanation_parts.append(
                f"## Feng Shui Score: {total}/100 ({grade})\n"
                f"- Command Position: {score.get('command_position', 0)}/30\n"
                f"- Five Elements Balance: {score.get('five_elements_balance', 0)}/20\n"
                f"- Chi Flow: {score.get('chi_flow', 0)}/25\n"
                f"- Sha Chi Avoidance: {score.get('sha_chi_avoidance', 0)}/25"
            )

        # --- Iterations ---
        if state.repair_iteration > 0:
            explanation_parts.append(
                f"\n*Pipeline completed in {state.repair_iteration} "
                f"repair iteration(s) ({state.elapsed_ms:.0f}ms total).*"
            )

        state.explanation = "\n\n".join(explanation_parts)

        yield self._emit_progress("Explanation complete", 1.0)
        yield self._emit_completed({
            "explanation_length": len(state.explanation),
            "total_score": sum(score.values()) if score else 0,
        })

    def _summarize_repairs(self, actions: list[RepairAction]) -> list[str]:
        lines = []
        for action in actions:
            if action.success:
                lines.append(f"- ✅ {action.description}")
            else:
                lines.append(f"- ❌ {action.description}")
        return lines or ["- No repairs applied"]

    def _summarize_unresolved(self, conflicts: list[Conflict]) -> list[str]:
        lines = []
        for c in conflicts:
            icon = "🔴" if c.severity == ConflictSeverity.CRITICAL else "🟡"
            lines.append(f"- {icon} {c.description}")
            if c.suggestion:
                lines.append(f"  → {c.suggestion}")
        return lines

    def _get_grade(self, total: int) -> str:
        if total >= GRADE_EXCELLENT:
            return "Excellent"
        if total >= GRADE_GOOD:
            return "Good"
        if total >= GRADE_FAIR:
            return "Needs Work"
        return "Poor"
