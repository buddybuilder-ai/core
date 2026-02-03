"""Tests for User Clarifier Tool."""

import pytest

from src.modules.layout.infrastructure.tools.user_clarifier_tool import (
    ClarificationAnswer,
    ClarificationQuestion,
    ClarifierInput,
    ClarifierOutput,
    QuestionPriority,
    QuestionStatus,
    QuestionType,
    UserClarifierTool,
)


class TestQuestionType:
    """Tests for QuestionType enum."""

    def test_question_types_exist(self) -> None:
        """Test all question types exist."""
        assert QuestionType.MULTIPLE_CHOICE == "multiple_choice"
        assert QuestionType.YES_NO == "yes_no"
        assert QuestionType.OPEN_ENDED == "open_ended"
        assert QuestionType.NUMERIC == "numeric"

    def test_enum_values_are_strings(self) -> None:
        """Test that enum values are strings."""
        for qt in QuestionType:
            assert isinstance(qt.value, str)


class TestQuestionPriority:
    """Tests for QuestionPriority enum."""

    def test_priority_levels_exist(self) -> None:
        """Test all priority levels exist."""
        assert QuestionPriority.REQUIRED == "required"
        assert QuestionPriority.RECOMMENDED == "recommended"
        assert QuestionPriority.OPTIONAL == "optional"


class TestQuestionStatus:
    """Tests for QuestionStatus enum."""

    def test_status_values_exist(self) -> None:
        """Test all status values exist."""
        assert QuestionStatus.PENDING == "pending"
        assert QuestionStatus.ANSWERED == "answered"
        assert QuestionStatus.SKIPPED == "skipped"


class TestClarificationQuestion:
    """Tests for ClarificationQuestion dataclass."""

    def test_create_multiple_choice_question(self) -> None:
        """Test creating a multiple choice question."""
        question = ClarificationQuestion(
            id="test_q1",
            question="What color do you prefer?",
            question_type=QuestionType.MULTIPLE_CHOICE,
            options=("Red", "Blue", "Green"),
        )
        assert question.id == "test_q1"
        assert question.question_type == QuestionType.MULTIPLE_CHOICE
        assert "Red" in question.options
        assert question.priority == QuestionPriority.RECOMMENDED

    def test_create_yes_no_question(self) -> None:
        """Test creating a yes/no question."""
        question = ClarificationQuestion(
            id="test_q2",
            question="Do you have pets?",
            question_type=QuestionType.YES_NO,
            priority=QuestionPriority.REQUIRED,
        )
        assert question.question_type == QuestionType.YES_NO
        assert question.priority == QuestionPriority.REQUIRED
        assert question.options == ()

    def test_create_numeric_question(self) -> None:
        """Test creating a numeric question."""
        question = ClarificationQuestion(
            id="test_q3",
            question="How many people live here?",
            question_type=QuestionType.NUMERIC,
            default_value="2",
        )
        assert question.question_type == QuestionType.NUMERIC
        assert question.default_value == "2"

    def test_create_open_ended_question(self) -> None:
        """Test creating an open-ended question."""
        question = ClarificationQuestion(
            id="test_q4",
            question="Any special requirements?",
            question_type=QuestionType.OPEN_ENDED,
            context="Please describe any accessibility needs",
        )
        assert question.question_type == QuestionType.OPEN_ENDED
        assert question.context == "Please describe any accessibility needs"

    def test_to_dict(self) -> None:
        """Test conversion to dictionary."""
        question = ClarificationQuestion(
            id="test_q1",
            question="Test question?",
            question_type=QuestionType.MULTIPLE_CHOICE,
            priority=QuestionPriority.OPTIONAL,
            options=("A", "B"),
            default_value="A",
            context="Test context",
            category="test",
        )
        result = question.to_dict()

        assert result["id"] == "test_q1"
        assert result["question"] == "Test question?"
        assert result["question_type"] == "multiple_choice"
        assert result["priority"] == "optional"
        assert result["options"] == ["A", "B"]
        assert result["default_value"] == "A"
        assert result["context"] == "Test context"
        assert result["category"] == "test"

    def test_question_is_frozen(self) -> None:
        """Test that question is immutable."""
        question = ClarificationQuestion(
            id="test", question="Test?", question_type=QuestionType.YES_NO
        )
        with pytest.raises(AttributeError):
            question.id = "modified"  # type: ignore


class TestClarificationQuestionValidation:
    """Tests for answer validation on ClarificationQuestion."""

    def test_validate_yes_no_valid_answers(self) -> None:
        """Test validation of valid yes/no answers."""
        question = ClarificationQuestion(
            id="q1", question="Test?", question_type=QuestionType.YES_NO
        )
        assert question.validate_answer("yes")
        assert question.validate_answer("no")
        assert question.validate_answer("y")
        assert question.validate_answer("n")
        assert question.validate_answer("true")
        assert question.validate_answer("false")
        assert question.validate_answer("YES")  # Case insensitive

    def test_validate_yes_no_invalid_answers(self) -> None:
        """Test validation rejects invalid yes/no answers."""
        question = ClarificationQuestion(
            id="q1", question="Test?", question_type=QuestionType.YES_NO
        )
        assert not question.validate_answer("maybe")
        assert not question.validate_answer("")
        assert not question.validate_answer("1")

    def test_validate_multiple_choice_valid(self) -> None:
        """Test validation of valid multiple choice answers."""
        question = ClarificationQuestion(
            id="q1",
            question="Test?",
            question_type=QuestionType.MULTIPLE_CHOICE,
            options=("Option A", "Option B", "Option C"),
        )
        assert question.validate_answer("Option A")
        assert question.validate_answer("Option B")
        assert question.validate_answer("Option C")

    def test_validate_multiple_choice_invalid(self) -> None:
        """Test validation rejects invalid multiple choice answers."""
        question = ClarificationQuestion(
            id="q1",
            question="Test?",
            question_type=QuestionType.MULTIPLE_CHOICE,
            options=("Option A", "Option B"),
        )
        assert not question.validate_answer("Option C")
        assert not question.validate_answer("option a")  # Case sensitive
        assert not question.validate_answer("")

    def test_validate_numeric_valid(self) -> None:
        """Test validation of valid numeric answers."""
        question = ClarificationQuestion(
            id="q1", question="Test?", question_type=QuestionType.NUMERIC
        )
        assert question.validate_answer("42")
        assert question.validate_answer("3.14")
        assert question.validate_answer("-5")
        assert question.validate_answer("0")

    def test_validate_numeric_invalid(self) -> None:
        """Test validation rejects invalid numeric answers."""
        question = ClarificationQuestion(
            id="q1", question="Test?", question_type=QuestionType.NUMERIC
        )
        assert not question.validate_answer("abc")
        assert not question.validate_answer("")
        assert not question.validate_answer("12.3.4")

    def test_validate_open_ended_valid(self) -> None:
        """Test validation of valid open-ended answers."""
        question = ClarificationQuestion(
            id="q1", question="Test?", question_type=QuestionType.OPEN_ENDED
        )
        assert question.validate_answer("Any text works")
        assert question.validate_answer("a")  # Single character is valid

    def test_validate_open_ended_invalid(self) -> None:
        """Test validation rejects empty open-ended answers."""
        question = ClarificationQuestion(
            id="q1", question="Test?", question_type=QuestionType.OPEN_ENDED
        )
        assert not question.validate_answer("")
        assert not question.validate_answer("   ")  # Whitespace only


class TestClarificationAnswer:
    """Tests for ClarificationAnswer dataclass."""

    def test_create_answered(self) -> None:
        """Test creating an answered response."""
        answer = ClarificationAnswer(
            question_id="q1",
            answer="yes",
            status=QuestionStatus.ANSWERED,
        )
        assert answer.question_id == "q1"
        assert answer.answer == "yes"
        assert answer.status == QuestionStatus.ANSWERED
        assert not answer.was_default

    def test_create_skipped_with_default(self) -> None:
        """Test creating a skipped response with default."""
        answer = ClarificationAnswer(
            question_id="q1",
            answer="default_value",
            status=QuestionStatus.SKIPPED,
            was_default=True,
        )
        assert answer.status == QuestionStatus.SKIPPED
        assert answer.was_default

    def test_to_dict(self) -> None:
        """Test conversion to dictionary."""
        answer = ClarificationAnswer(
            question_id="q1",
            answer="test",
            status=QuestionStatus.ANSWERED,
            was_default=False,
        )
        result = answer.to_dict()

        assert result["question_id"] == "q1"
        assert result["answer"] == "test"
        assert result["status"] == "answered"
        assert result["was_default"] is False


class TestClarifierInput:
    """Tests for ClarifierInput dataclass."""

    def test_default_values(self) -> None:
        """Test default input values."""
        input_data = ClarifierInput()
        assert input_data.questions == []
        assert input_data.answers == {}
        assert input_data.allow_skip is True
        assert input_data.auto_apply_defaults is True

    def test_with_questions_and_answers(self) -> None:
        """Test input with questions and pre-provided answers."""
        question = ClarificationQuestion(
            id="q1", question="Test?", question_type=QuestionType.YES_NO
        )
        input_data = ClarifierInput(
            questions=[question],
            answers={"q1": "yes"},
        )
        assert len(input_data.questions) == 1
        assert input_data.answers["q1"] == "yes"


class TestClarifierOutput:
    """Tests for ClarifierOutput dataclass."""

    @pytest.fixture
    def sample_output(self) -> ClarifierOutput:
        """Create sample output for testing."""
        return ClarifierOutput(
            resolved_answers=[
                ClarificationAnswer("q1", "yes", QuestionStatus.ANSWERED),
                ClarificationAnswer("q2", "default", QuestionStatus.SKIPPED, True),
            ],
            pending_questions=[
                ClarificationQuestion(
                    id="q3",
                    question="Pending?",
                    question_type=QuestionType.OPEN_ENDED,
                    priority=QuestionPriority.REQUIRED,
                    category="bedroom",
                ),
                ClarificationQuestion(
                    id="q4",
                    question="Also pending?",
                    question_type=QuestionType.YES_NO,
                    priority=QuestionPriority.OPTIONAL,
                    category="general",
                ),
            ],
            has_pending_required=True,
            all_resolved=False,
        )

    def test_get_answer_found(self, sample_output: ClarifierOutput) -> None:
        """Test getting an existing answer."""
        answer = sample_output.get_answer("q1")
        assert answer is not None
        assert answer.answer == "yes"

    def test_get_answer_not_found(self, sample_output: ClarifierOutput) -> None:
        """Test getting a non-existent answer."""
        answer = sample_output.get_answer("nonexistent")
        assert answer is None

    def test_get_answer_value_found(self, sample_output: ClarifierOutput) -> None:
        """Test getting answer value that exists."""
        value = sample_output.get_answer_value("q1")
        assert value == "yes"

    def test_get_answer_value_default(self, sample_output: ClarifierOutput) -> None:
        """Test getting answer value with default fallback."""
        value = sample_output.get_answer_value("nonexistent", "fallback")
        assert value == "fallback"

    def test_get_pending_by_category(self, sample_output: ClarifierOutput) -> None:
        """Test getting pending questions by category."""
        bedroom_qs = sample_output.get_pending_by_category("bedroom")
        assert len(bedroom_qs) == 1
        assert bedroom_qs[0].id == "q3"

        general_qs = sample_output.get_pending_by_category("general")
        assert len(general_qs) == 1

    def test_get_pending_required(self, sample_output: ClarifierOutput) -> None:
        """Test getting pending required questions."""
        required = sample_output.get_pending_required()
        assert len(required) == 1
        assert required[0].id == "q3"

    def test_all_resolved_when_empty_pending(self) -> None:
        """Test all_resolved is True when no pending questions."""
        output = ClarifierOutput(
            resolved_answers=[
                ClarificationAnswer("q1", "yes", QuestionStatus.ANSWERED)
            ],
            pending_questions=[],
            has_pending_required=False,
            all_resolved=True,
        )
        assert output.all_resolved


class TestUserClarifierTool:
    """Tests for UserClarifierTool."""

    @pytest.fixture
    def tool(self) -> UserClarifierTool:
        """Create tool instance."""
        return UserClarifierTool()

    def test_tool_properties(self, tool: UserClarifierTool) -> None:
        """Test tool name and description."""
        assert tool.name == "USER_CLARIFIER"
        assert "clarification" in tool.description.lower()

    def test_validate_input_empty(self, tool: UserClarifierTool) -> None:
        """Test validation of empty input."""
        input_data = ClarifierInput()
        errors = tool.validate_input(input_data)
        assert errors == []

    def test_validate_input_duplicate_ids(self, tool: UserClarifierTool) -> None:
        """Test validation catches duplicate question IDs."""
        q1 = ClarificationQuestion(
            id="same_id", question="Q1?", question_type=QuestionType.YES_NO
        )
        q2 = ClarificationQuestion(
            id="same_id", question="Q2?", question_type=QuestionType.NUMERIC
        )
        input_data = ClarifierInput(questions=[q1, q2])
        errors = tool.validate_input(input_data)
        assert any("Duplicate" in e for e in errors)

    def test_validate_input_multiple_choice_no_options(
        self, tool: UserClarifierTool
    ) -> None:
        """Test validation catches multiple choice without options."""
        question = ClarificationQuestion(
            id="q1",
            question="Choose?",
            question_type=QuestionType.MULTIPLE_CHOICE,
            options=(),  # No options
        )
        input_data = ClarifierInput(questions=[question])
        errors = tool.validate_input(input_data)
        assert any("no options" in e for e in errors)

    def test_validate_input_unknown_answer_reference(
        self, tool: UserClarifierTool
    ) -> None:
        """Test validation catches answers for unknown questions."""
        input_data = ClarifierInput(
            questions=[],
            answers={"unknown_q": "value"},
        )
        errors = tool.validate_input(input_data)
        assert any("unknown question" in e for e in errors)

    @pytest.mark.asyncio
    async def test_execute_with_provided_answers(
        self, tool: UserClarifierTool
    ) -> None:
        """Test execution with pre-provided answers."""
        question = ClarificationQuestion(
            id="q1",
            question="Do you want this?",
            question_type=QuestionType.YES_NO,
        )
        input_data = ClarifierInput(
            questions=[question],
            answers={"q1": "yes"},
        )

        result = await tool.execute(input_data)

        assert result.success
        assert result.data is not None
        assert result.data.all_resolved
        assert len(result.data.resolved_answers) == 1
        assert result.data.resolved_answers[0].answer == "yes"
        assert not result.data.resolved_answers[0].was_default

    @pytest.mark.asyncio
    async def test_execute_with_defaults_applied(
        self, tool: UserClarifierTool
    ) -> None:
        """Test execution applies defaults for optional questions."""
        question = ClarificationQuestion(
            id="q1",
            question="Optional question?",
            question_type=QuestionType.YES_NO,
            priority=QuestionPriority.OPTIONAL,
            default_value="no",
        )
        input_data = ClarifierInput(
            questions=[question],
            answers={},  # No answer provided
            auto_apply_defaults=True,
            allow_skip=True,
        )

        result = await tool.execute(input_data)

        assert result.success
        assert result.data is not None
        assert result.data.all_resolved
        assert result.data.resolved_answers[0].answer == "no"
        assert result.data.resolved_answers[0].was_default
        assert result.data.resolved_answers[0].status == QuestionStatus.SKIPPED

    @pytest.mark.asyncio
    async def test_execute_required_stays_pending(
        self, tool: UserClarifierTool
    ) -> None:
        """Test required questions without answers stay pending."""
        question = ClarificationQuestion(
            id="q1",
            question="Required question?",
            question_type=QuestionType.OPEN_ENDED,
            priority=QuestionPriority.REQUIRED,
            default_value="default",  # Has default but is required
        )
        input_data = ClarifierInput(
            questions=[question],
            answers={},
            auto_apply_defaults=True,
        )

        result = await tool.execute(input_data)

        assert result.success
        assert result.data is not None
        assert not result.data.all_resolved
        assert result.data.has_pending_required
        assert len(result.data.pending_questions) == 1

    @pytest.mark.asyncio
    async def test_execute_invalid_answer_stays_pending(
        self, tool: UserClarifierTool
    ) -> None:
        """Test questions with invalid answers stay pending."""
        question = ClarificationQuestion(
            id="q1",
            question="Choose one?",
            question_type=QuestionType.MULTIPLE_CHOICE,
            options=("A", "B", "C"),
        )
        input_data = ClarifierInput(
            questions=[question],
            answers={"q1": "D"},  # Invalid option
        )

        result = await tool.execute(input_data)

        assert result.success
        assert result.data is not None
        assert not result.data.all_resolved
        assert len(result.data.pending_questions) == 1

    @pytest.mark.asyncio
    async def test_execute_no_defaults_when_disabled(
        self, tool: UserClarifierTool
    ) -> None:
        """Test defaults not applied when auto_apply_defaults is False."""
        question = ClarificationQuestion(
            id="q1",
            question="Optional?",
            question_type=QuestionType.YES_NO,
            priority=QuestionPriority.OPTIONAL,
            default_value="yes",
        )
        input_data = ClarifierInput(
            questions=[question],
            answers={},
            auto_apply_defaults=False,
        )

        result = await tool.execute(input_data)

        assert result.success
        assert result.data is not None
        assert not result.data.all_resolved
        assert len(result.data.pending_questions) == 1

    @pytest.mark.asyncio
    async def test_execute_no_defaults_when_skip_disabled(
        self, tool: UserClarifierTool
    ) -> None:
        """Test defaults not applied when allow_skip is False."""
        question = ClarificationQuestion(
            id="q1",
            question="Optional?",
            question_type=QuestionType.YES_NO,
            priority=QuestionPriority.OPTIONAL,
            default_value="yes",
        )
        input_data = ClarifierInput(
            questions=[question],
            answers={},
            allow_skip=False,
        )

        result = await tool.execute(input_data)

        assert result.success
        assert result.data is not None
        assert not result.data.all_resolved
        assert len(result.data.pending_questions) == 1

    @pytest.mark.asyncio
    async def test_execute_mixed_questions(self, tool: UserClarifierTool) -> None:
        """Test execution with mix of answered, defaulted, and pending."""
        questions = [
            ClarificationQuestion(
                id="answered",
                question="Answered?",
                question_type=QuestionType.YES_NO,
            ),
            ClarificationQuestion(
                id="defaulted",
                question="Defaulted?",
                question_type=QuestionType.YES_NO,
                priority=QuestionPriority.OPTIONAL,
                default_value="no",
            ),
            ClarificationQuestion(
                id="pending",
                question="Pending?",
                question_type=QuestionType.OPEN_ENDED,
                priority=QuestionPriority.REQUIRED,
            ),
        ]
        input_data = ClarifierInput(
            questions=questions,
            answers={"answered": "yes"},
        )

        result = await tool.execute(input_data)

        assert result.success
        assert result.data is not None
        assert len(result.data.resolved_answers) == 2
        assert len(result.data.pending_questions) == 1
        assert result.data.has_pending_required
        assert not result.data.all_resolved

    @pytest.mark.asyncio
    async def test_execute_metadata(self, tool: UserClarifierTool) -> None:
        """Test execution metadata is populated."""
        questions = [
            ClarificationQuestion(
                id="q1", question="Q1?", question_type=QuestionType.YES_NO
            ),
            ClarificationQuestion(
                id="q2",
                question="Q2?",
                question_type=QuestionType.YES_NO,
                priority=QuestionPriority.OPTIONAL,
                default_value="no",
            ),
        ]
        input_data = ClarifierInput(questions=questions, answers={"q1": "yes"})

        result = await tool.execute(input_data)

        assert result.metadata["questions_received"] == 2
        assert result.metadata["answers_resolved"] == 2
        assert result.metadata["questions_pending"] == 0
        assert result.metadata["has_pending_required"] is False


class TestUserClarifierToolHelpers:
    """Tests for UserClarifierTool helper methods."""

    @pytest.fixture
    def tool(self) -> UserClarifierTool:
        """Create tool instance."""
        return UserClarifierTool()

    def test_get_predefined_question_exists(self, tool: UserClarifierTool) -> None:
        """Test getting an existing predefined question."""
        question = tool.get_predefined_question("budget_level")
        assert question is not None
        assert question.id == "budget_level"
        assert question.question_type == QuestionType.MULTIPLE_CHOICE

    def test_get_predefined_question_not_exists(self, tool: UserClarifierTool) -> None:
        """Test getting a non-existent predefined question."""
        question = tool.get_predefined_question("nonexistent")
        assert question is None

    def test_get_questions_for_room_type_bedroom(
        self, tool: UserClarifierTool
    ) -> None:
        """Test getting questions for bedroom."""
        questions = tool.get_questions_for_room_type("bedroom")
        categories = {q.category for q in questions}
        assert "bedroom" in categories or "general" in categories
        # Should include bed position preference
        ids = {q.id for q in questions}
        assert "bed_position_preference" in ids

    def test_get_questions_for_room_type_office(self, tool: UserClarifierTool) -> None:
        """Test getting questions for office."""
        questions = tool.get_questions_for_room_type("office")
        ids = {q.id for q in questions}
        assert "desk_facing_preference" in ids
        assert "work_style" in ids

    def test_get_questions_for_room_type_living_room(
        self, tool: UserClarifierTool
    ) -> None:
        """Test getting questions for living room."""
        questions = tool.get_questions_for_room_type("living_room")
        ids = {q.id for q in questions}
        assert "sofa_configuration" in ids

    def test_get_questions_for_room_type_includes_general(
        self, tool: UserClarifierTool
    ) -> None:
        """Test that general questions are included for any room type."""
        questions = tool.get_questions_for_room_type("bedroom")
        categories = {q.category for q in questions}
        assert "general" in categories

    def test_create_custom_question(self, tool: UserClarifierTool) -> None:
        """Test creating a custom question."""
        question = tool.create_custom_question(
            question="Custom question?",
            question_type=QuestionType.MULTIPLE_CHOICE,
            priority=QuestionPriority.REQUIRED,
            options=("Option 1", "Option 2"),
            default_value="Option 1",
            context="Custom context",
            category="custom_category",
        )

        assert question.id.startswith("custom_")
        assert question.question == "Custom question?"
        assert question.question_type == QuestionType.MULTIPLE_CHOICE
        assert question.priority == QuestionPriority.REQUIRED
        assert question.options == ("Option 1", "Option 2")
        assert question.default_value == "Option 1"
        assert question.context == "Custom context"
        assert question.category == "custom_category"

    def test_create_custom_question_unique_ids(self, tool: UserClarifierTool) -> None:
        """Test that custom questions get unique IDs."""
        q1 = tool.create_custom_question(
            question="Q1?", question_type=QuestionType.YES_NO
        )
        q2 = tool.create_custom_question(
            question="Q2?", question_type=QuestionType.YES_NO
        )
        assert q1.id != q2.id


class TestUserClarifierToolPredefinedQuestions:
    """Tests for predefined questions in UserClarifierTool."""

    @pytest.fixture
    def tool(self) -> UserClarifierTool:
        """Create tool instance."""
        return UserClarifierTool()

    def test_predefined_questions_have_defaults(
        self, tool: UserClarifierTool
    ) -> None:
        """Test that all predefined questions have default values."""
        for qid, question in tool.PREDEFINED_QUESTIONS.items():
            assert question.default_value is not None, f"{qid} missing default"

    def test_predefined_multiple_choice_have_options(
        self, tool: UserClarifierTool
    ) -> None:
        """Test multiple choice questions have options."""
        for qid, question in tool.PREDEFINED_QUESTIONS.items():
            if question.question_type == QuestionType.MULTIPLE_CHOICE:
                assert len(question.options) > 0, f"{qid} missing options"

    def test_predefined_questions_have_context(self, tool: UserClarifierTool) -> None:
        """Test that predefined questions have context."""
        for qid, question in tool.PREDEFINED_QUESTIONS.items():
            assert question.context, f"{qid} missing context"

    def test_predefined_bed_position(self, tool: UserClarifierTool) -> None:
        """Test bed position preference question."""
        q = tool.PREDEFINED_QUESTIONS["bed_position_preference"]
        assert q.category == "bedroom"
        assert "command position" in q.default_value.lower()
        assert len(q.options) >= 3

    def test_predefined_desk_facing(self, tool: UserClarifierTool) -> None:
        """Test desk facing preference question."""
        q = tool.PREDEFINED_QUESTIONS["desk_facing_preference"]
        assert q.category == "office"
        assert "door" in q.default_value.lower()

    def test_predefined_dining_capacity_is_required(
        self, tool: UserClarifierTool
    ) -> None:
        """Test dining capacity is a required question."""
        q = tool.PREDEFINED_QUESTIONS["dining_capacity"]
        assert q.priority == QuestionPriority.REQUIRED
        assert q.question_type == QuestionType.NUMERIC


class TestUserClarifierToolLangChainSchema:
    """Tests for LangChain tool schema."""

    def test_langchain_schema_structure(self) -> None:
        """Test LangChain schema has correct structure."""
        tool = UserClarifierTool()
        schema = tool.to_langchain_tool_schema()

        assert schema["name"] == "USER_CLARIFIER"
        assert "description" in schema
        assert "parameters" in schema
        assert schema["parameters"]["type"] == "object"
        assert "questions" in schema["parameters"]["properties"]
        assert "answers" in schema["parameters"]["properties"]
        assert "questions" in schema["parameters"]["required"]

    def test_langchain_schema_question_type_enum(self) -> None:
        """Test schema includes question type enum values."""
        tool = UserClarifierTool()
        schema = tool.to_langchain_tool_schema()

        question_props = schema["parameters"]["properties"]["questions"]["items"][
            "properties"
        ]
        assert "question_type" in question_props
        enum_values = question_props["question_type"]["enum"]
        assert "multiple_choice" in enum_values
        assert "yes_no" in enum_values


class TestUserClarifierToolIntegration:
    """Integration tests for UserClarifierTool."""

    @pytest.mark.asyncio
    async def test_full_clarification_flow(self) -> None:
        """Test a complete clarification flow with predefined questions."""
        tool = UserClarifierTool()

        # Get questions for bedroom
        questions = tool.get_questions_for_room_type("bedroom")

        # First pass - provide some answers
        input_data = ClarifierInput(
            questions=questions,
            answers={
                "bed_position_preference": "Command position (diagonal from door)",
                "budget_level": "Medium",
            },
            auto_apply_defaults=True,
        )

        result = await tool.execute(input_data)

        assert result.success
        assert result.data is not None

        # Check that answered questions are resolved
        bed_answer = result.data.get_answer("bed_position_preference")
        assert bed_answer is not None
        assert not bed_answer.was_default

        budget_answer = result.data.get_answer("budget_level")
        assert budget_answer is not None
        assert not budget_answer.was_default

    @pytest.mark.asyncio
    async def test_safe_execute(self) -> None:
        """Test safe_execute wrapper handles errors gracefully."""
        tool = UserClarifierTool()
        input_data = ClarifierInput()

        result = await tool.safe_execute(input_data)

        assert result.success
        assert result.data is not None
        assert result.data.all_resolved

    @pytest.mark.asyncio
    async def test_execution_time_tracking(self) -> None:
        """Test that execution time is tracked."""
        tool = UserClarifierTool()
        input_data = ClarifierInput(
            questions=[
                ClarificationQuestion(
                    id="q1", question="Test?", question_type=QuestionType.YES_NO
                )
            ],
            answers={"q1": "yes"},
        )

        result = await tool.execute(input_data)

        assert result.execution_time_ms is not None
        assert result.execution_time_ms >= 0
