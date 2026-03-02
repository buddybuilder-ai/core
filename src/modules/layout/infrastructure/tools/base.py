"""Base tool abstract class for feng shui layout agent."""

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Generic, TypeVar

TInput = TypeVar("TInput")
TOutput = TypeVar("TOutput")


class ToolError(Exception):
    """Base exception for tool errors."""

    def __init__(self, tool_name: str, message: str) -> None:
        self.tool_name = tool_name
        self.message = message
        super().__init__(f"[{tool_name}] {message}")


class ToolInputError(ToolError):
    """Exception raised for invalid tool input."""

    def __init__(
        self, tool_name: str, message: str, invalid_fields: list[str] | None = None
    ) -> None:
        super().__init__(tool_name, message)
        self.invalid_fields = invalid_fields or []


class ToolTimeoutError(ToolError):
    """Exception raised when tool execution times out."""

    def __init__(self, tool_name: str, timeout_seconds: float) -> None:
        super().__init__(tool_name, f"Execution timed out after {timeout_seconds}s")
        self.timeout_seconds = timeout_seconds


@dataclass(frozen=True)
class ToolResult(Generic[TOutput]):
    """Result of a tool execution.

    Attributes:
        success: Whether the tool execution was successful.
        data: The output data if successful, None otherwise.
        error: Error message if failed, None otherwise.
        execution_time_ms: Time taken to execute the tool in milliseconds.
        metadata: Additional metadata about the execution.
        timestamp: When the tool was executed.
    """

    success: bool
    data: TOutput | None = None
    error: str | None = None
    execution_time_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def __post_init__(self) -> None:
        """Validate result state."""
        if self.success and self.data is None:
            raise ValueError("Successful result must have data")
        if not self.success and self.error is None:
            raise ValueError("Failed result must have error message")

    @classmethod
    def ok(
        cls,
        data: TOutput,
        execution_time_ms: float = 0.0,
        metadata: dict[str, Any] | None = None,
    ) -> "ToolResult[TOutput]":
        """Create a successful result."""
        return cls(
            success=True,
            data=data,
            execution_time_ms=execution_time_ms,
            metadata=metadata or {},
        )

    @classmethod
    def fail(
        cls,
        error: str,
        execution_time_ms: float = 0.0,
        metadata: dict[str, Any] | None = None,
    ) -> "ToolResult[TOutput]":
        """Create a failed result."""
        return cls(
            success=False,
            error=error,
            execution_time_ms=execution_time_ms,
            metadata=metadata or {},
        )

    def unwrap(self) -> TOutput:
        """Get the data or raise an error if failed.

        Returns:
            The data if successful.

        Raises:
            ValueError: If the result is a failure.
        """
        if not self.success:
            raise ValueError(f"Cannot unwrap failed result: {self.error}")
        # Type narrowing - we know data is not None when success is True
        assert self.data is not None
        return self.data

    def unwrap_or(self, default: TOutput) -> TOutput:
        """Get the data or return a default value if failed.

        Args:
            default: The default value to return if failed.

        Returns:
            The data if successful, otherwise the default value.
        """
        if self.success and self.data is not None:
            return self.data
        return default

    def map(self, func: Callable[[TOutput], Any]) -> "ToolResult[Any]":
        """Transform the data if successful.

        Args:
            func: Function to transform the data.

        Returns:
            New ToolResult with transformed data or the same error.
        """
        if self.success and self.data is not None:
            try:
                new_data = func(self.data)
                return ToolResult.ok(
                    data=new_data,
                    execution_time_ms=self.execution_time_ms,
                    metadata=self.metadata,
                )
            except Exception as e:
                return ToolResult.fail(
                    error=str(e),
                    execution_time_ms=self.execution_time_ms,
                    metadata=self.metadata,
                )
        return ToolResult.fail(
            error=self.error or "Unknown error",
            execution_time_ms=self.execution_time_ms,
            metadata=self.metadata,
        )


class BaseTool(ABC, Generic[TInput, TOutput]):
    """Abstract base class for all feng shui layout tools.

    This class provides a common interface for all tools used by the
    feng shui layout agent. Each tool must implement the execute method.

    Type Parameters:
        TInput: The type of input the tool accepts.
        TOutput: The type of output the tool produces.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the unique name of this tool."""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """Return a description of what this tool does.

        This description is used by the LLM to understand when to use the tool.
        """
        ...

    @property
    def version(self) -> str:
        """Return the version of this tool."""
        return "1.0.0"

    @abstractmethod
    async def execute(self, input_data: TInput) -> ToolResult[TOutput]:
        """Execute the tool with the given input.

        Args:
            input_data: The input data for the tool.

        Returns:
            A ToolResult containing either the output data or an error.
        """
        ...

    @abstractmethod
    def validate_input(self, input_data: TInput) -> list[str]:
        """Validate the input data.

        Args:
            input_data: The input data to validate.

        Returns:
            A list of validation error messages. Empty list if valid.
        """
        ...

    async def safe_execute(self, input_data: TInput) -> ToolResult[TOutput]:
        """Execute the tool with input validation and error handling.

        This method validates input before execution and catches any
        exceptions, converting them to ToolResult failures.

        Args:
            input_data: The input data for the tool.

        Returns:
            A ToolResult containing either the output data or an error.
        """
        import time

        start_time = time.perf_counter()

        # Validate input first
        validation_errors = self.validate_input(input_data)
        if validation_errors:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            return ToolResult.fail(
                error=f"Input validation failed: {'; '.join(validation_errors)}",
                execution_time_ms=elapsed_ms,
                metadata={"validation_errors": validation_errors},
            )

        try:
            result = await self.execute(input_data)
            return result
        except ToolError as e:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            return ToolResult.fail(
                error=str(e),
                execution_time_ms=elapsed_ms,
                metadata={"exception_type": type(e).__name__},
            )
        except Exception as e:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            return ToolResult.fail(
                error=f"Unexpected error: {str(e)}",
                execution_time_ms=elapsed_ms,
                metadata={"exception_type": type(e).__name__},
            )

    def to_langchain_tool_schema(self) -> dict[str, Any]:
        """Convert this tool to a LangChain-compatible tool schema.

        Returns:
            A dictionary representing the tool in LangChain format.
        """
        return {
            "name": self.name,
            "description": self.description,
        }

    def __repr__(self) -> str:
        """Return string representation of the tool."""
        return f"{self.__class__.__name__}(name={self.name!r}, version={self.version!r})"
