"""Step 5: Explainer.

Summarizes the layout generation process in natural Thai language using an
LLM call styled to the current personality mode (mentor/buddy/fun).

Falls back to a template-based English summary if the LLM call fails, so
the pipeline always produces an explanation.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from typing import Any

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
from src.modules.layout.application.services.kua_calculator import (
    calculate_kua,
    kua_auspicious_walls,
    kua_best_direction_info,
)
from src.modules.layout.infrastructure.geometry import AABB
from src.modules.layout.infrastructure.llm.langchain_agent import FengShuiLLMAgent

logger = logging.getLogger(__name__)

# Feng shui grade thresholds
GRADE_EXCELLENT = 80
GRADE_GOOD = 60
GRADE_FAIR = 40


class ExplainerStep(BaseStep):
    """Step 5: Generate a personality-styled Thai explanation of layout decisions."""

    step = PipelineStep.EXPLAINER

    def __init__(self, config: PipelineConfig) -> None:
        super().__init__(config)
        self._llm_agent = FengShuiLLMAgent()

    async def execute(self, state: PipelineState) -> AsyncGenerator[SSEEvent, None]:
        yield self._emit_started()
        yield self._emit_progress("Generating explanation...", 0.3)

        logger.info("📝 STEP 5: Generating layout explanation")

        summary = self._build_summary(state)

        yield self._emit_progress("Calling LLM for explanation...", 0.6)

        logger.info(f"   kua_line = {summary['kua_line']!r}")
        try:
            llm_response = await self._llm_agent.explain_layout(
                total_score=summary["total_score"],
                grade=summary["grade"],
                remaining_issues=summary["remaining_issues"],
                kua_line=summary["kua_line"],
                personality_mode=state.personality_mode,
            )
            state.explanation = llm_response.content
            logger.info(
                f"   ✓ LLM explanation generated "
                f"({len(state.explanation)} chars, mode={state.personality_mode!r})"
            )
            logger.info(f"   LLM raw: {state.explanation[:300]!r}")
        except Exception as exc:
            logger.warning(f"   explain_layout LLM failed — using template fallback: {exc}")
            state.explanation = self._template_explanation(summary, state)

        total_score = summary["total_score"]
        grade = summary["grade"]
        logger.info(f"   Final Score: {total_score}/100 ({grade})")
        logger.info(
            f"   Conflicts: "
            f"{len([c for c in state.conflicts if c.resolved])} resolved, "
            f"{len(state.unresolved_conflicts)} remaining"
        )

        yield self._emit_progress("Explanation complete", 1.0)
        yield self._emit_completed(
            {
                "explanation_length": len(state.explanation),
                "total_score": total_score,
                "personality_mode": state.personality_mode,
            }
        )

    # ------------------------------------------------------------------
    # Summary builder
    # ------------------------------------------------------------------

    def _build_summary(self, state: PipelineState) -> dict[str, Any]:
        """Extract structured data from state for the LLM prompt and fallback template."""
        items = state.layout_items
        spec = state.room_spec
        room_type = spec.get("room_type", "room")
        width = spec.get("width", 0)
        depth = spec.get("depth", 0)

        # Items summary
        names = [i.get("name", i.get("furniture_type", "item")) for i in items]
        items_summary = f"{len(items)} items: {', '.join(names)}" if names else "no items placed"

        # Final geometric overlap safety-net: regardless of what the
        # pipeline conflict list says, verify the actual AABB layout right
        # now so the explanation never claims "no collisions" when furniture
        # visually overlaps.
        actual_overlaps = self._count_actual_overlaps(items)

        # Conflicts
        all_conflicts = state.conflicts
        resolved = [c for c in all_conflicts if c.resolved]
        unresolved = state.unresolved_conflicts

        if actual_overlaps > 0 and not unresolved:
            # Pipeline thinks everything is resolved, but geometry says
            # otherwise → override the summary so the LLM does NOT claim
            # the layout is collision-free.
            conflicts_summary = (
                f"{actual_overlaps} furniture overlap(s) still present in final layout"
            )
            remaining_issues_override = (
                f"{actual_overlaps} furniture overlap(s) remain — "
                "some items are too close or overlapping"
            )
        elif all_conflicts:
            conflicts_summary = (
                f"{len(all_conflicts)} conflicts found, "
                f"{len(resolved)} resolved, {len(unresolved)} remaining"
            )
            remaining_issues_override = None
        else:
            conflicts_summary = "no conflicts detected"
            remaining_issues_override = None

        # Repairs
        repair_descs = [a.description for a in state.repair_actions if a.success]
        repairs_summary = "; ".join(repair_descs) if repair_descs else "no repairs needed"

        # Score / grade
        score = state.feng_shui_score
        total_score = sum(score.values()) if score else 0
        grade = self._get_grade(total_score)

        # Remaining issues
        if remaining_issues_override:
            remaining_issues = remaining_issues_override
        elif unresolved:
            issue_descs = [c.description for c in unresolved]
            remaining_issues = "; ".join(issue_descs)
        else:
            remaining_issues = "none"

        # Kua line — pre-rendered Thai text
        user_prefs = spec.get("user_preferences") or {}
        birth_year = user_prefs.get("birth_year")
        gender = user_prefs.get("gender", "")
        kua_line = "ลองกรอกปีเกิดและเพศในการตั้งค่าห้อง เพื่อให้เราปรับทิศหัวเตียงตามเลขกัวส่วนตัวของคุณได้"
        if birth_year and gender:
            try:
                kua = calculate_kua(int(birth_year), gender)
                info = kua_best_direction_info(kua)
                kua_line = f"หัวเตียงหันทิศ{info['wall_th']}ตามเลขกัว {kua} เสริม{info['benefit']}ให้คุณโดยตรง"
            except Exception:
                pass

        return {
            "room_type": room_type,
            "width": width,
            "depth": depth,
            "items_summary": items_summary,
            "conflicts_summary": conflicts_summary,
            "repairs_summary": repairs_summary,
            "total_score": total_score,
            "grade": grade,
            "remaining_issues": remaining_issues,
            "kua_line": kua_line,
        }

    # ------------------------------------------------------------------
    # Template fallback (original behaviour, English)
    # ------------------------------------------------------------------

    def _template_explanation(self, summary: dict[str, Any], state: PipelineState) -> str:
        """Produce a structured markdown explanation without an LLM call."""
        parts: list[str] = []

        room_type = summary["room_type"]
        width = summary["width"]
        depth = summary["depth"]
        items = state.layout_items

        parts.append(
            f"## Layout Summary\n"
            f"Generated layout for **{room_type}** ({width}m × {depth}m) "
            f"with **{len(items)} furniture items** placed."
        )

        categories: dict[str, list[str]] = {}
        for item in items:
            cat = item.get("category", "other")
            categories.setdefault(cat, []).append(item.get("name", ""))
        if categories:
            cat_lines = [f"- **{cat}**: {', '.join(names)}" for cat, names in categories.items()]
            parts.append("### Items Placed\n" + "\n".join(cat_lines))

        all_conflicts = state.conflicts
        resolved = [c for c in all_conflicts if c.resolved]
        unresolved = state.unresolved_conflicts
        if all_conflicts:
            parts.append(
                f"## Conflicts\n"
                f"Found **{len(all_conflicts)} conflicts** total. "
                f"Resolved **{len(resolved)}**, remaining **{len(unresolved)}**."
            )
            if resolved:
                repair_lines = self._summarize_repairs(state.repair_actions)
                parts.append("### Repairs Applied\n" + "\n".join(repair_lines))
            if unresolved:
                issue_lines = self._summarize_unresolved(unresolved)
                parts.append("### Remaining Issues\n" + "\n".join(issue_lines))
        else:
            parts.append("## Conflicts\nNo conflicts detected — clean layout!")

        total_score = summary["total_score"]
        grade = summary["grade"]
        score = state.feng_shui_score
        if score:
            parts.append(
                f"## Feng Shui Score: {total_score}/100 ({grade})\n"
                f"- Command Position: {score.get('command_position', 0)}/30\n"
                f"- Five Elements Balance: {score.get('five_elements_balance', 0)}/20\n"
                f"- Chi Flow: {score.get('chi_flow', 0)}/25\n"
                f"- Sha Chi Avoidance: {score.get('sha_chi_avoidance', 0)}/25"
            )

        if state.repair_iteration > 0:
            parts.append(
                f"\n*Pipeline completed in {state.repair_iteration} "
                f"repair iteration(s) ({state.elapsed_ms:.0f}ms total).*"
            )

        return "\n\n".join(parts)

    # ------------------------------------------------------------------
    # Small helpers
    # ------------------------------------------------------------------

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

    @staticmethod
    def _footprint(dims: dict[str, Any], rotation: int) -> tuple[float, float]:
        """Return (fw, fd) footprint in room space — same logic as RuleCheckerStep."""
        w = dims.get("width", 1.0)
        d = dims.get("depth", 1.0)
        if rotation % 360 in (90, 270):
            return d, w
        return w, d

    def _count_actual_overlaps(self, items: list[dict[str, Any]]) -> int:
        """Quick geometric overlap count on final layout items."""
        boxes: list[AABB] = []
        for item in items:
            fw, fd = self._footprint(
                item.get("dimensions", {}), item.get("rotation", 0)
            )
            boxes.append(
                AABB.from_center_and_size(
                    item.get("pos_x", 0.0),
                    item.get("pos_z", 0.0),
                    fw,
                    fd,
                )
            )
        count = 0
        for i, a in enumerate(boxes):
            for b in boxes[i + 1 :]:
                if a.intersects(b):
                    count += 1
        return count

    def _get_grade(self, total: int) -> str:
        if total >= GRADE_EXCELLENT:
            return "Excellent"
        if total >= GRADE_GOOD:
            return "Good"
        if total >= GRADE_FAIR:
            return "Needs Work"
        return "Poor"
