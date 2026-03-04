"""User clarifier tool for feng shui layout agent."""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any
from uuid import uuid4

from src.modules.layout.infrastructure.tools.base import BaseTool, ToolResult


class QuestionType(StrEnum):
    """Types of clarification questions."""

    MULTIPLE_CHOICE = "multiple_choice"
    YES_NO = "yes_no"
    OPEN_ENDED = "open_ended"
    NUMERIC = "numeric"


class QuestionPriority(StrEnum):
    """Priority levels for clarification questions."""

    REQUIRED = "required"
    RECOMMENDED = "recommended"
    OPTIONAL = "optional"


class QuestionStatus(StrEnum):
    """Status of a clarification question."""

    PENDING = "pending"
    ANSWERED = "answered"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class ClarificationQuestion:
    """A question to ask the user for clarification.

    Attributes:
        id: Unique question identifier.
        question: The question text.
        question_type: Type of question.
        priority: How important is this question.
        options: Available options for multiple choice.
        default_value: Default value if user skips.
        context: Additional context for the question.
        category: Category for grouping related questions.
    """

    id: str
    question: str
    question_type: QuestionType
    priority: QuestionPriority = QuestionPriority.RECOMMENDED
    options: tuple[str, ...] = ()
    default_value: str | None = None
    context: str = ""
    category: str = "general"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "question": self.question,
            "question_type": self.question_type.value,
            "priority": self.priority.value,
            "options": list(self.options),
            "default_value": self.default_value,
            "context": self.context,
            "category": self.category,
        }

    def validate_answer(self, answer: str) -> bool:
        """Check if an answer is valid for this question type."""
        if self.question_type == QuestionType.YES_NO:
            return answer.lower() in {"yes", "no", "y", "n", "true", "false"}
        if self.question_type == QuestionType.MULTIPLE_CHOICE:
            return answer in self.options
        if self.question_type == QuestionType.NUMERIC:
            try:
                float(answer)
                return True
            except ValueError:
                return False
        # Open ended - any non-empty answer is valid
        return len(answer.strip()) > 0


@dataclass(frozen=True)
class ClarificationAnswer:
    """An answer to a clarification question.

    Attributes:
        question_id: ID of the answered question.
        answer: The user's answer.
        status: Status of the answer.
        was_default: Whether the default value was used.
    """

    question_id: str
    answer: str
    status: QuestionStatus
    was_default: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "question_id": self.question_id,
            "answer": self.answer,
            "status": self.status.value,
            "was_default": self.was_default,
        }


@dataclass
class ClarifierInput:
    """Input for the user clarifier tool.

    Attributes:
        questions: Questions to ask the user.
        answers: Pre-provided answers (for batch processing).
        allow_skip: Whether to allow skipping optional questions.
        auto_apply_defaults: Automatically apply defaults for skipped questions.
    """

    questions: list[ClarificationQuestion] = field(default_factory=list)
    answers: dict[str, str] = field(default_factory=dict)
    allow_skip: bool = True
    auto_apply_defaults: bool = True


@dataclass(frozen=True)
class ClarifierOutput:
    """Output of the user clarifier tool.

    Attributes:
        resolved_answers: All resolved answers.
        pending_questions: Questions still needing answers.
        has_pending_required: Whether there are required questions pending.
        all_resolved: Whether all questions have been resolved.
    """

    resolved_answers: list[ClarificationAnswer]
    pending_questions: list[ClarificationQuestion]
    has_pending_required: bool
    all_resolved: bool

    def get_answer(self, question_id: str) -> ClarificationAnswer | None:
        """Get answer for a specific question."""
        for answer in self.resolved_answers:
            if answer.question_id == question_id:
                return answer
        return None

    def get_answer_value(self, question_id: str, default: str = "") -> str:
        """Get answer value for a question, or default if not found."""
        answer = self.get_answer(question_id)
        return answer.answer if answer else default

    def get_pending_by_category(self, category: str) -> list[ClarificationQuestion]:
        """Get pending questions in a specific category."""
        return [q for q in self.pending_questions if q.category == category]

    def get_pending_required(self) -> list[ClarificationQuestion]:
        """Get pending required questions."""
        return [q for q in self.pending_questions if q.priority == QuestionPriority.REQUIRED]


class UserClarifierTool(BaseTool[ClarifierInput, ClarifierOutput]):
    """Tool for asking users clarification questions.

    This tool manages the flow of clarification questions during
    layout generation. It:
    - Collects questions from the agent
    - Matches pre-provided answers
    - Applies default values when appropriate
    - Tracks which questions still need answers
    """

    # Predefined questions for studio apartment layout
    # All questions are category="studio_apartment" so they fire for this room type.
    # Questions are shown in priority order: REQUIRED first, then RECOMMENDED.
    PREDEFINED_QUESTIONS: dict[str, ClarificationQuestion] = {
        # --- REQUIRED -------------------------------------------------------
        "sleep_zone_preference": ClarificationQuestion(
            id="sleep_zone_preference",
            question="โซนนอนควรอยู่ส่วนไหนของห้อง?",
            question_type=QuestionType.MULTIPLE_CHOICE,
            priority=QuestionPriority.REQUIRED,
            options=(
                "ผนังด้านตรงข้ามประตู (ตำแหน่งผู้บัญชาการ)",
                "ผนังด้านซ้ายของประตู",
                "ผนังด้านขวาของประตู",
                "ไม่มีความชอบพิเศษ",
            ),
            default_value="ผนังด้านตรงข้ามประตู (ตำแหน่งผู้บัญชาการ)",
            context="ตำแหน่งผู้บัญชาการคือมองเห็นประตูโดยไม่ตรงแนวประตู เหมาะกับฮ้วงจุ้ยที่สุด",
            category="studio_apartment",
        ),
        # --- RECOMMENDED ----------------------------------------------------
        "work_area_needed": ClarificationQuestion(
            id="work_area_needed",
            question="ต้องการโซนทำงาน (โต๊ะ/เก้าอี้) ในห้องด้วยไหม?",
            question_type=QuestionType.YES_NO,
            priority=QuestionPriority.RECOMMENDED,
            default_value="yes",
            context="ถ้าต้องการจะจัดวางโต๊ะพับหรือโต๊ะขนาดกะทัดรัดเข้าไปด้วย",
            category="studio_apartment",
        ),
        "sofa_bed_or_separate": ClarificationQuestion(
            id="sofa_bed_or_separate",
            question="ต้องการเตียงแยกหรือโซฟาเตียง (sofa bed)?",
            question_type=QuestionType.MULTIPLE_CHOICE,
            priority=QuestionPriority.RECOMMENDED,
            options=(
                "โซฟาเตียง (ประหยัดพื้นที่)",
                "เตียงแยก + โซฟาแยก",
                "เตียงเดี่ยว (ไม่ต้องการโซฟา)",
            ),
            default_value="โซฟาเตียง (ประหยัดพื้นที่)",
            context="ส่งผลต่อการจัดวางโซนนอนและโซนนั่งเล่น",
            category="studio_apartment",
        ),
        "budget_level": ClarificationQuestion(
            id="budget_level",
            question="งบประมาณสำหรับเฟอร์นิเจอร์อยู่ในระดับไหน?",
            question_type=QuestionType.MULTIPLE_CHOICE,
            priority=QuestionPriority.RECOMMENDED,
            options=("ประหยัด", "กลาง", "สูง"),
            default_value="กลาง",
            context="ส่งผลต่อการเลือกรายการเฟอร์นิเจอร์จาก catalog",
            category="studio_apartment",
        ),
    }

    @property
    def name(self) -> str:
        return "USER_CLARIFIER"

    @property
    def description(self) -> str:
        return (
            "Asks users clarification questions to better understand their "
            "preferences and requirements for the feng shui layout. Returns "
            "answers and pending questions that still need user input."
        )

    def validate_input(self, input_data: ClarifierInput) -> list[str]:
        """Validate clarifier input."""
        errors = []

        # Check for duplicate question IDs
        question_ids = [q.id for q in input_data.questions]
        if len(question_ids) != len(set(question_ids)):
            errors.append("Duplicate question IDs found")

        # Validate multiple choice questions have options
        for q in input_data.questions:
            if q.question_type == QuestionType.MULTIPLE_CHOICE and not q.options:
                errors.append(f"Multiple choice question '{q.id}' has no options")

        # Validate provided answers reference existing questions
        valid_ids = {q.id for q in input_data.questions}
        for answer_id in input_data.answers:
            if answer_id not in valid_ids:
                errors.append(f"Answer provided for unknown question: {answer_id}")

        return errors

    async def execute(self, input_data: ClarifierInput) -> ToolResult[ClarifierOutput]:
        """Execute the clarifier tool."""
        import time

        start_time = time.perf_counter()

        resolved_answers: list[ClarificationAnswer] = []
        pending_questions: list[ClarificationQuestion] = []

        for question in input_data.questions:
            # Check if answer was provided
            if question.id in input_data.answers:
                provided_answer = input_data.answers[question.id]
                if question.validate_answer(provided_answer):
                    resolved_answers.append(
                        ClarificationAnswer(
                            question_id=question.id,
                            answer=provided_answer,
                            status=QuestionStatus.ANSWERED,
                            was_default=False,
                        )
                    )
                else:
                    # Invalid answer - still pending
                    pending_questions.append(question)
            elif (
                input_data.auto_apply_defaults
                and input_data.allow_skip
                and question.default_value is not None
                and question.priority != QuestionPriority.REQUIRED
            ):
                # Apply default for non-required questions
                resolved_answers.append(
                    ClarificationAnswer(
                        question_id=question.id,
                        answer=question.default_value,
                        status=QuestionStatus.SKIPPED,
                        was_default=True,
                    )
                )
            else:
                # Question needs user input
                pending_questions.append(question)

        has_pending_required = any(
            q.priority == QuestionPriority.REQUIRED for q in pending_questions
        )
        all_resolved = len(pending_questions) == 0

        elapsed_ms = (time.perf_counter() - start_time) * 1000

        output = ClarifierOutput(
            resolved_answers=resolved_answers,
            pending_questions=pending_questions,
            has_pending_required=has_pending_required,
            all_resolved=all_resolved,
        )

        return ToolResult.ok(
            data=output,
            execution_time_ms=elapsed_ms,
            metadata={
                "questions_received": len(input_data.questions),
                "answers_resolved": len(resolved_answers),
                "questions_pending": len(pending_questions),
                "has_pending_required": has_pending_required,
            },
        )

    def get_predefined_question(self, question_id: str) -> ClarificationQuestion | None:
        """Get a predefined question by ID."""
        return self.PREDEFINED_QUESTIONS.get(question_id)

    def get_questions_for_room_type(self, room_type: str) -> list[ClarificationQuestion]:
        """Get relevant predefined questions for a room type, sorted by priority."""
        _PRIORITY_ORDER = {
            QuestionPriority.REQUIRED: 0,
            QuestionPriority.RECOMMENDED: 1,
            QuestionPriority.OPTIONAL: 2,
        }
        questions = [
            q
            for q in self.PREDEFINED_QUESTIONS.values()
            if q.category == room_type or q.category == "general"
        ]
        return sorted(questions, key=lambda q: _PRIORITY_ORDER[q.priority])

    def create_custom_question(
        self,
        question: str,
        question_type: QuestionType,
        *,
        priority: QuestionPriority = QuestionPriority.RECOMMENDED,
        options: tuple[str, ...] = (),
        default_value: str | None = None,
        context: str = "",
        category: str = "custom",
    ) -> ClarificationQuestion:
        """Create a custom clarification question."""
        return ClarificationQuestion(
            id=f"custom_{uuid4().hex[:8]}",
            question=question,
            question_type=question_type,
            priority=priority,
            options=options,
            default_value=default_value,
            context=context,
            category=category,
        )

    def to_langchain_tool_schema(self) -> dict[str, Any]:
        """Convert to LangChain tool schema."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "questions": {
                        "type": "array",
                        "description": "List of clarification questions to ask",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "question": {"type": "string"},
                                "question_type": {
                                    "type": "string",
                                    "enum": [t.value for t in QuestionType],
                                },
                                "priority": {
                                    "type": "string",
                                    "enum": [p.value for p in QuestionPriority],
                                },
                                "options": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                            },
                        },
                    },
                    "answers": {
                        "type": "object",
                        "description": "Pre-provided answers keyed by question ID",
                    },
                },
                "required": ["questions"],
            },
        }
