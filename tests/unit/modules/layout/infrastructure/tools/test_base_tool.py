"""Tests for base tool abstract class."""

from dataclasses import dataclass
from datetime import datetime

import pytest

from src.modules.layout.infrastructure.tools.base import (
    BaseTool,
    ToolError,
    ToolInputError,
    ToolResult,
    ToolTimeoutError,
)


class TestToolError:
    """Tests for ToolError exception."""

    def test_error_message_format(self) -> None:
        """Test that error message includes tool name."""
        error = ToolError("TEST_TOOL", "Something went wrong")
        assert str(error) == "[TEST_TOOL] Something went wrong"
        assert error.tool_name == "TEST_TOOL"
        assert error.message == "Something went wrong"

    def test_error_inheritance(self) -> None:
        """Test that ToolError inherits from Exception."""
        error = ToolError("TOOL", "Error")
        assert isinstance(error, Exception)


class TestToolInputError:
    """Tests for ToolInputError exception."""

    def test_input_error_with_fields(self) -> None:
        """Test input error with invalid fields."""
        error = ToolInputError(
            "VALIDATOR",
            "Invalid input",
            invalid_fields=["width", "depth"],
        )
        assert error.tool_name == "VALIDATOR"
        assert error.invalid_fields == ["width", "depth"]

    def test_input_error_without_fields(self) -> None:
        """Test input error without invalid fields."""
        error = ToolInputError("VALIDATOR", "Invalid input")
        assert error.invalid_fields == []

    def test_input_error_inheritance(self) -> None:
        """Test that ToolInputError inherits from ToolError."""
        error = ToolInputError("TOOL", "Error")
        assert isinstance(error, ToolError)


class TestToolTimeoutError:
    """Tests for ToolTimeoutError exception."""

    def test_timeout_error_message(self) -> None:
        """Test timeout error message format."""
        error = ToolTimeoutError("RAG_SEARCH", 30.0)
        assert "timed out" in str(error)
        assert "30.0s" in str(error)
        assert error.timeout_seconds == 30.0

    def test_timeout_error_inheritance(self) -> None:
        """Test that ToolTimeoutError inherits from ToolError."""
        error = ToolTimeoutError("TOOL", 10.0)
        assert isinstance(error, ToolError)


class TestToolResult:
    """Tests for ToolResult dataclass."""

    def test_successful_result(self) -> None:
        """Test creating successful result."""
        result = ToolResult(
            success=True,
            data={"items": [1, 2, 3]},
            execution_time_ms=100.5,
        )
        assert result.success is True
        assert result.data == {"items": [1, 2, 3]}
        assert result.error is None
        assert result.execution_time_ms == 100.5

    def test_failed_result(self) -> None:
        """Test creating failed result."""
        result = ToolResult(
            success=False,
            error="Connection timeout",
            execution_time_ms=5000.0,
        )
        assert result.success is False
        assert result.data is None
        assert result.error == "Connection timeout"

    def test_result_with_metadata(self) -> None:
        """Test result with custom metadata."""
        result = ToolResult(
            success=True,
            data="output",
            metadata={"retries": 2, "cache_hit": False},
        )
        assert result.metadata["retries"] == 2
        assert result.metadata["cache_hit"] is False

    def test_result_has_timestamp(self) -> None:
        """Test that result has timestamp."""
        result = ToolResult(success=True, data="test")
        assert isinstance(result.timestamp, datetime)

    def test_successful_result_requires_data(self) -> None:
        """Test that successful result must have data."""
        with pytest.raises(ValueError, match="must have data"):
            ToolResult(success=True, data=None)

    def test_failed_result_requires_error(self) -> None:
        """Test that failed result must have error."""
        with pytest.raises(ValueError, match="must have error"):
            ToolResult(success=False, error=None)

    def test_result_is_immutable(self) -> None:
        """Test that result is immutable (frozen)."""
        result = ToolResult(success=True, data="test")
        with pytest.raises(AttributeError):
            result.success = False  # type: ignore

    def test_ok_factory_method(self) -> None:
        """Test ToolResult.ok factory method."""
        result = ToolResult.ok(
            data={"value": 42},
            execution_time_ms=50.0,
            metadata={"source": "cache"},
        )
        assert result.success is True
        assert result.data == {"value": 42}
        assert result.execution_time_ms == 50.0
        assert result.metadata["source"] == "cache"

    def test_fail_factory_method(self) -> None:
        """Test ToolResult.fail factory method."""
        result = ToolResult.fail(
            error="Database error",
            execution_time_ms=100.0,
            metadata={"db_code": 1234},
        )
        assert result.success is False
        assert result.error == "Database error"
        assert result.execution_time_ms == 100.0
        assert result.metadata["db_code"] == 1234

    def test_unwrap_on_success(self) -> None:
        """Test unwrap returns data on success."""
        result = ToolResult.ok(data=[1, 2, 3])
        assert result.unwrap() == [1, 2, 3]

    def test_unwrap_on_failure_raises(self) -> None:
        """Test unwrap raises on failure."""
        result = ToolResult.fail(error="Failed")
        with pytest.raises(ValueError, match="Cannot unwrap"):
            result.unwrap()

    def test_unwrap_or_on_success(self) -> None:
        """Test unwrap_or returns data on success."""
        result = ToolResult.ok(data="actual")
        assert result.unwrap_or("default") == "actual"

    def test_unwrap_or_on_failure(self) -> None:
        """Test unwrap_or returns default on failure."""
        result = ToolResult.fail(error="Failed")
        assert result.unwrap_or("default") == "default"

    def test_map_on_success(self) -> None:
        """Test map transforms data on success."""
        result = ToolResult.ok(data=10)
        mapped = result.map(lambda x: x * 2)
        assert mapped.success is True
        assert mapped.data == 20

    def test_map_on_failure(self) -> None:
        """Test map preserves error on failure."""
        result = ToolResult.fail(error="Original error")
        mapped = result.map(lambda x: x * 2)
        assert mapped.success is False
        assert mapped.error == "Original error"

    def test_map_handles_exception(self) -> None:
        """Test map handles exception in transform function."""
        result = ToolResult.ok(data=10)
        mapped = result.map(lambda x: x / 0)  # Will raise ZeroDivisionError
        assert mapped.success is False
        assert "division by zero" in mapped.error.lower()


@dataclass
class SampleInput:
    """Sample input for testing."""

    value: int
    name: str


@dataclass
class SampleOutput:
    """Sample output for testing."""

    result: str
    processed: bool


class SampleTool(BaseTool[SampleInput, SampleOutput]):
    """Sample tool implementation for testing."""

    def __init__(self, should_fail: bool = False, validation_errors: list[str] | None = None) -> None:
        self._should_fail = should_fail
        self._validation_errors = validation_errors or []

    @property
    def name(self) -> str:
        return "SAMPLE_TOOL"

    @property
    def description(self) -> str:
        return "A sample tool for testing purposes"

    @property
    def version(self) -> str:
        return "1.2.3"

    async def execute(self, input_data: SampleInput) -> ToolResult[SampleOutput]:
        if self._should_fail:
            return ToolResult.fail(error="Intentional failure")
        output = SampleOutput(
            result=f"Processed: {input_data.name} = {input_data.value}",
            processed=True,
        )
        return ToolResult.ok(data=output, execution_time_ms=10.0)

    def validate_input(self, input_data: SampleInput) -> list[str]:
        return self._validation_errors


class RaisingTool(BaseTool[SampleInput, SampleOutput]):
    """Tool that raises an exception during execution."""

    @property
    def name(self) -> str:
        return "RAISING_TOOL"

    @property
    def description(self) -> str:
        return "A tool that raises exceptions"

    async def execute(self, input_data: SampleInput) -> ToolResult[SampleOutput]:
        raise RuntimeError("Something went wrong")

    def validate_input(self, input_data: SampleInput) -> list[str]:
        return []


class ToolErrorTool(BaseTool[SampleInput, SampleOutput]):
    """Tool that raises a ToolError during execution."""

    @property
    def name(self) -> str:
        return "TOOL_ERROR_TOOL"

    @property
    def description(self) -> str:
        return "A tool that raises ToolError"

    async def execute(self, input_data: SampleInput) -> ToolResult[SampleOutput]:
        raise ToolError("TOOL_ERROR_TOOL", "Custom tool error")

    def validate_input(self, input_data: SampleInput) -> list[str]:
        return []


class TestBaseTool:
    """Tests for BaseTool abstract class."""

    @pytest.mark.asyncio
    async def test_execute_success(self) -> None:
        """Test successful tool execution."""
        tool = SampleTool()
        input_data = SampleInput(value=42, name="test")
        result = await tool.execute(input_data)

        assert result.success is True
        assert result.data is not None
        assert result.data.result == "Processed: test = 42"
        assert result.data.processed is True

    @pytest.mark.asyncio
    async def test_execute_failure(self) -> None:
        """Test failed tool execution."""
        tool = SampleTool(should_fail=True)
        input_data = SampleInput(value=1, name="fail")
        result = await tool.execute(input_data)

        assert result.success is False
        assert result.error == "Intentional failure"

    def test_tool_name_property(self) -> None:
        """Test tool name property."""
        tool = SampleTool()
        assert tool.name == "SAMPLE_TOOL"

    def test_tool_description_property(self) -> None:
        """Test tool description property."""
        tool = SampleTool()
        assert "sample tool" in tool.description.lower()

    def test_tool_version_property(self) -> None:
        """Test tool version property."""
        tool = SampleTool()
        assert tool.version == "1.2.3"

    def test_tool_repr(self) -> None:
        """Test tool string representation."""
        tool = SampleTool()
        repr_str = repr(tool)
        assert "SampleTool" in repr_str
        assert "SAMPLE_TOOL" in repr_str
        assert "1.2.3" in repr_str

    @pytest.mark.asyncio
    async def test_safe_execute_success(self) -> None:
        """Test safe_execute on successful execution."""
        tool = SampleTool()
        input_data = SampleInput(value=10, name="safe")
        result = await tool.safe_execute(input_data)

        assert result.success is True
        assert result.data is not None

    @pytest.mark.asyncio
    async def test_safe_execute_with_validation_errors(self) -> None:
        """Test safe_execute catches validation errors."""
        tool = SampleTool(validation_errors=["value must be positive", "name is required"])
        input_data = SampleInput(value=-1, name="")
        result = await tool.safe_execute(input_data)

        assert result.success is False
        assert "validation failed" in result.error.lower()
        assert "value must be positive" in result.error
        assert result.metadata["validation_errors"] == ["value must be positive", "name is required"]

    @pytest.mark.asyncio
    async def test_safe_execute_catches_exceptions(self) -> None:
        """Test safe_execute catches unexpected exceptions."""
        tool = RaisingTool()
        input_data = SampleInput(value=1, name="test")
        result = await tool.safe_execute(input_data)

        assert result.success is False
        assert "unexpected error" in result.error.lower()
        assert "something went wrong" in result.error.lower()
        assert result.metadata["exception_type"] == "RuntimeError"

    @pytest.mark.asyncio
    async def test_safe_execute_catches_tool_error(self) -> None:
        """Test safe_execute catches ToolError."""
        tool = ToolErrorTool()
        input_data = SampleInput(value=1, name="test")
        result = await tool.safe_execute(input_data)

        assert result.success is False
        assert "custom tool error" in result.error.lower()
        assert result.metadata["exception_type"] == "ToolError"

    @pytest.mark.asyncio
    async def test_safe_execute_measures_time(self) -> None:
        """Test safe_execute measures execution time."""
        tool = SampleTool()
        input_data = SampleInput(value=1, name="test")
        result = await tool.safe_execute(input_data)

        assert result.execution_time_ms >= 0

    def test_to_langchain_tool_schema(self) -> None:
        """Test conversion to LangChain tool schema."""
        tool = SampleTool()
        schema = tool.to_langchain_tool_schema()

        assert schema["name"] == "SAMPLE_TOOL"
        assert "sample tool" in schema["description"].lower()


class TestToolResultChaining:
    """Tests for ToolResult chaining operations."""

    def test_chain_multiple_maps(self) -> None:
        """Test chaining multiple map operations."""
        result = ToolResult.ok(data=5)
        chained = result.map(lambda x: x * 2).map(lambda x: x + 10).map(lambda x: str(x))

        assert chained.success is True
        assert chained.data == "20"

    def test_chain_stops_at_failure(self) -> None:
        """Test that chain stops processing after failure."""
        result = ToolResult.ok(data=5)
        chained = (
            result.map(lambda x: x * 2)
            .map(lambda x: x / 0)  # Fails here
            .map(lambda x: x + 100)  # Should not run
        )

        assert chained.success is False
        assert "division by zero" in chained.error.lower()
