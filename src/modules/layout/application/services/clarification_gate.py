"""Clarification gate — decides whether to ask the user questions before running the pipeline.

Returns a list of pending ClarificationQuestion dicts (ready for SSE serialisation),
or an empty list if no questions are needed.

App scope: studio apartment only.  room_type is always "studio_apartment".

Intents that bypass the gate (layout context already known):
  rearrange_all, explain, question, set_mode, modify
"""

from __future__ import annotations

from src.modules.layout.infrastructure.tools.user_clarifier_tool import (
    QuestionPriority,
    UserClarifierTool,
)

_TOOL = UserClarifierTool()

# App is studio-apartment only — room_type never needs to be asked
_ROOM_TYPE = "studio_apartment"

# Intents that never need clarification
_BYPASS_INTENTS = {"rearrange_all", "explain", "question", "set_mode", "modify"}


def get_pending_questions(
    intent: str,
    clarification_answers: dict[str, str],
    has_existing_layout: bool = False,
) -> list[dict]:
    """Return serialised pending ClarificationQuestion dicts, or [] if none needed.

    Asks REQUIRED questions first; only after all REQUIRED are answered will
    RECOMMENDED questions appear (up to 3 per round).

    Args:
        intent: Classified intent from RouterAgent.
        clarification_answers: Map of question_id → answer already provided.
        has_existing_layout: Whether an existing layout is present.
            rearrange_all/modify bypass the gate only when layout already exists.

    Returns:
        List of question dicts (ClarificationQuestion.to_dict()) to ask,
        or empty list if the pipeline should proceed directly.
    """
    # Intents that always bypass (layout context is already known)
    if intent in {"explain", "question", "set_mode"}:
        return []

    # modify/rearrange_all bypass only when an existing layout is present;
    # when there's no layout they fall through to new_layout pipeline and
    # need clarification just like new_layout.
    if intent in {"modify", "rearrange_all"} and has_existing_layout:
        return []

    all_questions = _TOOL.get_questions_for_room_type(_ROOM_TYPE)

    # REQUIRED unanswered questions must be resolved before RECOMMENDED ones
    required_pending = [
        q for q in all_questions
        if q.priority == QuestionPriority.REQUIRED
        and q.id not in clarification_answers
    ]
    if required_pending:
        return [q.to_dict() for q in required_pending[:3]]

    # All REQUIRED answered — surface RECOMMENDED ones next
    recommended_pending = [
        q for q in all_questions
        if q.priority == QuestionPriority.RECOMMENDED
        and q.id not in clarification_answers
    ]
    if recommended_pending:
        return [q.to_dict() for q in recommended_pending[:3]]

    return []
