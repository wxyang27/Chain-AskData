"""SQL Executor abstract interface.

Current default: MockExecutor (dry-run only, returns placeholder).
Future: MaxComputeExecutor (DataWorks ODPS SQL, read-only, with
timeout / row-limit / table-whitelist safety controls).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ExecutionResult:
    """Result of a SQL execution."""

    success: bool
    sql: str = ""
    columns: list[str] = field(default_factory=list)
    rows: list[list[Any]] = field(default_factory=list)
    row_count: int = 0
    error_message: str = ""
    execution_ms: int = 0
    dry_run: bool = True


class ExecutorClient(ABC):
    """Abstract SQL executor.

    Concrete implementations:
        MockExecutor       — dry-run, validates SQL syntax, returns placeholder
        MaxComputeExecutor — ODPS SQL read-only, with safety controls
    """

    @abstractmethod
    def execute(self, sql: str, *, timeout_seconds: int = 30, max_rows: int = 1000) -> ExecutionResult:
        """Execute SQL and return structured result."""
        ...

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Human-readable provider name for tracing."""
        ...

    @property
    @abstractmethod
    def is_readonly(self) -> bool:
        """Whether this executor only allows read operations."""
        ...
