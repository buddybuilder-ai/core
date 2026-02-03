"""Tests for RAG search tool."""

import pytest

from src.modules.layout.infrastructure.tools.feng_shui_rules_data import (
    FENG_SHUI_RULES,
    FengShuiRule,
    RuleCategory,
    get_rules_by_category,
    get_rules_for_furniture,
    get_rules_for_room_type,
    search_rules_by_keywords,
)
from src.modules.layout.infrastructure.tools.rag_search_tool import (
    MockRagSearchTool,
    RagSearchInput,
    RagSearchOutput,
    RuleSearchResult,
)


class TestFengShuiRulesData:
    """Tests for feng shui rules data module."""

    def test_rules_exist(self) -> None:
        """Test that rules are defined."""
        assert len(FENG_SHUI_RULES) > 0

    def test_rule_structure(self) -> None:
        """Test that rules have required fields."""
        for rule in FENG_SHUI_RULES:
            assert rule.id
            assert rule.category
            assert rule.title
            assert rule.description
            assert rule.priority > 0

    def test_rule_categories_covered(self) -> None:
        """Test that all categories have at least one rule."""
        categories = {r.category for r in FENG_SHUI_RULES}
        assert RuleCategory.COMMAND_POSITION in categories
        assert RuleCategory.FIVE_ELEMENTS in categories
        assert RuleCategory.CHI_FLOW in categories
        assert RuleCategory.SHA_CHI in categories

    def test_get_rules_by_category(self) -> None:
        """Test filtering rules by category."""
        command_rules = get_rules_by_category(RuleCategory.COMMAND_POSITION)
        assert len(command_rules) > 0
        assert all(r.category == RuleCategory.COMMAND_POSITION for r in command_rules)

    def test_get_rules_for_room_type(self) -> None:
        """Test filtering rules by room type."""
        bedroom_rules = get_rules_for_room_type("bedroom")
        assert len(bedroom_rules) > 0

        # Check that bedroom-specific rules are included
        bed_rule_ids = {r.id for r in bedroom_rules}
        assert "cmd_002" in bed_rule_ids  # Bed command position

    def test_get_rules_for_furniture(self) -> None:
        """Test filtering rules by furniture type."""
        bed_rules = get_rules_for_furniture("bed")
        assert len(bed_rules) > 0
        assert any("bed" in r.title.lower() or "bed" in r.description.lower() for r in bed_rules)

    def test_search_rules_by_keywords(self) -> None:
        """Test keyword search."""
        results = search_rules_by_keywords(["command", "position"])
        assert len(results) > 0

        # First result should have highest match count
        first_rule, first_count = results[0]
        for rule, count in results[1:]:
            assert count <= first_count

    def test_search_with_no_matches(self) -> None:
        """Test search with no matching keywords."""
        results = search_rules_by_keywords(["xyzabc123"])
        assert len(results) == 0


class TestRuleSearchResult:
    """Tests for RuleSearchResult dataclass."""

    def test_result_creation(self) -> None:
        """Test creating a search result."""
        result = RuleSearchResult(
            rule_id="cmd_001",
            title="Test Rule",
            description="A test rule description",
            category="command_position",
            priority=90,
            relevance_score=0.85,
            applicable_furniture=["bed", "desk"],
        )
        assert result.rule_id == "cmd_001"
        assert result.relevance_score == 0.85

    def test_result_to_dict(self) -> None:
        """Test result serialization."""
        result = RuleSearchResult(
            rule_id="cmd_001",
            title="Test Rule",
            description="Description",
            category="command_position",
            priority=90,
            relevance_score=0.85,
            applicable_furniture=["bed"],
        )
        d = result.to_dict()
        assert d["rule_id"] == "cmd_001"
        assert d["relevance_score"] == 0.85


class TestRagSearchOutput:
    """Tests for RagSearchOutput dataclass."""

    def test_output_has_results(self) -> None:
        """Test has_results property."""
        output_with_results = RagSearchOutput(
            results=[
                RuleSearchResult(
                    rule_id="1",
                    title="Test",
                    description="Test",
                    category="test",
                    priority=50,
                    relevance_score=0.5,
                    applicable_furniture=[],
                )
            ],
            total_matches=1,
            query_processed="test",
        )
        assert output_with_results.has_results is True

        output_without_results = RagSearchOutput(
            results=[],
            total_matches=0,
            query_processed="test",
        )
        assert output_without_results.has_results is False

    def test_get_top_result(self) -> None:
        """Test getting top result."""
        results = [
            RuleSearchResult(
                rule_id="1",
                title="First",
                description="First",
                category="test",
                priority=90,
                relevance_score=0.9,
                applicable_furniture=[],
            ),
            RuleSearchResult(
                rule_id="2",
                title="Second",
                description="Second",
                category="test",
                priority=80,
                relevance_score=0.7,
                applicable_furniture=[],
            ),
        ]
        output = RagSearchOutput(
            results=results,
            total_matches=2,
            query_processed="test",
        )
        top = output.get_top_result()
        assert top is not None
        assert top.rule_id == "1"

    def test_get_top_result_empty(self) -> None:
        """Test getting top result when empty."""
        output = RagSearchOutput(
            results=[],
            total_matches=0,
            query_processed="test",
        )
        assert output.get_top_result() is None

    def test_get_results_by_category(self) -> None:
        """Test filtering results by category."""
        results = [
            RuleSearchResult(
                rule_id="1",
                title="Test1",
                description="Test1",
                category="command_position",
                priority=90,
                relevance_score=0.9,
                applicable_furniture=[],
            ),
            RuleSearchResult(
                rule_id="2",
                title="Test2",
                description="Test2",
                category="chi_flow",
                priority=80,
                relevance_score=0.7,
                applicable_furniture=[],
            ),
        ]
        output = RagSearchOutput(
            results=results,
            total_matches=2,
            query_processed="test",
        )
        command_results = output.get_results_by_category("command_position")
        assert len(command_results) == 1
        assert command_results[0].rule_id == "1"


class TestMockRagSearchTool:
    """Tests for MockRagSearchTool."""

    @pytest.fixture
    def tool(self) -> MockRagSearchTool:
        """Create mock RAG search tool instance."""
        return MockRagSearchTool()

    def test_tool_name(self, tool: MockRagSearchTool) -> None:
        """Test tool name property."""
        assert tool.name == "RAG_SEARCH"

    def test_tool_description(self, tool: MockRagSearchTool) -> None:
        """Test tool description property."""
        assert "feng shui" in tool.description.lower()
        assert "knowledge" in tool.description.lower()

    def test_validate_input_valid(self, tool: MockRagSearchTool) -> None:
        """Test validation with valid input."""
        input_data = RagSearchInput(query="bed placement")
        errors = tool.validate_input(input_data)
        assert errors == []

    def test_validate_input_empty_query(self, tool: MockRagSearchTool) -> None:
        """Test validation with empty query."""
        input_data = RagSearchInput(query="")
        errors = tool.validate_input(input_data)
        assert len(errors) > 0
        assert any("empty" in e.lower() for e in errors)

    def test_validate_input_max_results_too_low(self, tool: MockRagSearchTool) -> None:
        """Test validation with max_results too low."""
        input_data = RagSearchInput(query="test", max_results=0)
        errors = tool.validate_input(input_data)
        assert len(errors) > 0

    def test_validate_input_max_results_too_high(self, tool: MockRagSearchTool) -> None:
        """Test validation with max_results too high."""
        input_data = RagSearchInput(query="test", max_results=100)
        errors = tool.validate_input(input_data)
        assert len(errors) > 0

    @pytest.mark.asyncio
    async def test_basic_search(self, tool: MockRagSearchTool) -> None:
        """Test basic search functionality."""
        input_data = RagSearchInput(query="command position bed")
        result = await tool.execute(input_data)

        assert result.success is True
        assert result.data is not None
        assert result.data.has_results is True
        assert len(result.data.results) > 0

    @pytest.mark.asyncio
    async def test_search_returns_relevant_results(self, tool: MockRagSearchTool) -> None:
        """Test that search returns relevant results."""
        input_data = RagSearchInput(query="bed command position")
        result = await tool.execute(input_data)

        assert result.success is True
        assert result.data.has_results is True

        # Should find bed command position rule
        top_result = result.data.get_top_result()
        assert top_result is not None
        assert "bed" in top_result.title.lower() or "command" in top_result.title.lower()

    @pytest.mark.asyncio
    async def test_search_with_room_type_filter(self, tool: MockRagSearchTool) -> None:
        """Test search with room type filter."""
        input_data = RagSearchInput(
            query="furniture placement",
            room_type="bedroom",
        )
        result = await tool.execute(input_data)

        assert result.success is True
        # All results should be applicable to bedroom
        for r in result.data.results:
            # Get the original rule to check room types
            rule = tool.get_rule_by_id(r.rule_id)
            if rule:
                assert "bedroom" in rule.room_types or len(rule.room_types) == 0

    @pytest.mark.asyncio
    async def test_search_with_furniture_filter(self, tool: MockRagSearchTool) -> None:
        """Test search with furniture type filter."""
        input_data = RagSearchInput(
            query="placement",
            furniture_types=["bed"],
        )
        result = await tool.execute(input_data)

        assert result.success is True
        # Should find rules about bed placement
        assert result.data.has_results is True

    @pytest.mark.asyncio
    async def test_search_with_category_filter(self, tool: MockRagSearchTool) -> None:
        """Test search with category filter."""
        input_data = RagSearchInput(
            query="energy flow",
            categories=[RuleCategory.CHI_FLOW],
        )
        result = await tool.execute(input_data)

        assert result.success is True
        # All results should be in chi_flow category
        for r in result.data.results:
            assert r.category == "chi_flow"

    @pytest.mark.asyncio
    async def test_search_max_results(self, tool: MockRagSearchTool) -> None:
        """Test that max_results is respected."""
        input_data = RagSearchInput(
            query="furniture",
            max_results=3,
        )
        result = await tool.execute(input_data)

        assert result.success is True
        assert len(result.data.results) <= 3

    @pytest.mark.asyncio
    async def test_search_with_no_matches(self, tool: MockRagSearchTool) -> None:
        """Test search with no matching results."""
        input_data = RagSearchInput(
            query="xyznonexistent123",
            room_type="bedroom",
            categories=[RuleCategory.COMMAND_POSITION],
        )
        result = await tool.execute(input_data)

        assert result.success is True
        # May or may not have results depending on filters
        assert result.data is not None

    @pytest.mark.asyncio
    async def test_search_returns_metadata(self, tool: MockRagSearchTool) -> None:
        """Test that search returns metadata."""
        input_data = RagSearchInput(query="bed position")
        result = await tool.execute(input_data)

        assert result.success is True
        assert "query" in result.metadata
        assert "keywords" in result.metadata
        assert "total_matches" in result.metadata

    @pytest.mark.asyncio
    async def test_search_measures_time(self, tool: MockRagSearchTool) -> None:
        """Test that execution time is measured."""
        input_data = RagSearchInput(query="feng shui")
        result = await tool.execute(input_data)

        assert result.success is True
        assert result.execution_time_ms >= 0

    @pytest.mark.asyncio
    async def test_results_sorted_by_relevance(self, tool: MockRagSearchTool) -> None:
        """Test that results are sorted by relevance score."""
        input_data = RagSearchInput(query="command position")
        result = await tool.execute(input_data)

        assert result.success is True
        if len(result.data.results) > 1:
            for i in range(len(result.data.results) - 1):
                assert (
                    result.data.results[i].relevance_score
                    >= result.data.results[i + 1].relevance_score
                )

    def test_get_all_rules(self, tool: MockRagSearchTool) -> None:
        """Test getting all rules."""
        rules = tool.get_all_rules()
        assert len(rules) == len(FENG_SHUI_RULES)

    def test_get_rule_by_id(self, tool: MockRagSearchTool) -> None:
        """Test getting rule by ID."""
        rule = tool.get_rule_by_id("cmd_001")
        assert rule is not None
        assert rule.id == "cmd_001"

    def test_get_rule_by_id_not_found(self, tool: MockRagSearchTool) -> None:
        """Test getting non-existent rule."""
        rule = tool.get_rule_by_id("nonexistent")
        assert rule is None

    def test_to_langchain_tool_schema(self, tool: MockRagSearchTool) -> None:
        """Test LangChain tool schema conversion."""
        schema = tool.to_langchain_tool_schema()

        assert schema["name"] == "RAG_SEARCH"
        assert "parameters" in schema
        assert "query" in schema["parameters"]["properties"]
        assert "room_type" in schema["parameters"]["properties"]


class TestRuleCategories:
    """Tests for rule categories in knowledge base."""

    def test_command_position_rules(self) -> None:
        """Test command position rules exist and are valid."""
        rules = get_rules_by_category(RuleCategory.COMMAND_POSITION)
        assert len(rules) >= 3
        assert any("bed" in r.title.lower() for r in rules)
        assert any("desk" in r.title.lower() for r in rules)

    def test_five_elements_rules(self) -> None:
        """Test five elements rules exist."""
        rules = get_rules_by_category(RuleCategory.FIVE_ELEMENTS)
        assert len(rules) >= 2
        # Should mention elements
        all_text = " ".join(r.description.lower() for r in rules)
        assert "wood" in all_text
        assert "fire" in all_text
        assert "water" in all_text

    def test_chi_flow_rules(self) -> None:
        """Test chi flow rules exist."""
        rules = get_rules_by_category(RuleCategory.CHI_FLOW)
        assert len(rules) >= 2
        # Should mention chi or energy
        all_text = " ".join(r.description.lower() for r in rules)
        assert "chi" in all_text or "energy" in all_text

    def test_sha_chi_rules(self) -> None:
        """Test sha chi rules exist."""
        rules = get_rules_by_category(RuleCategory.SHA_CHI)
        assert len(rules) >= 2
        # Should mention sha chi or poison arrows
        all_text = " ".join(r.description.lower() for r in rules)
        assert "sha" in all_text or "poison" in all_text or "sharp" in all_text
