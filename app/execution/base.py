"""Abstract SQL executor interface."""

from abc import ABC, abstractmethod

from app.execution.objects import SqlExecutionRequest, SqlExecutionResult


class SqlExecutor(ABC):
    """Pluggable executor used by the pipeline execution stage."""

    @property
    @abstractmethod
    def mode(self) -> str:
        """Execution mode name, e.g. disabled/mock/sqlite/maxcompute."""
        ...

    @property
    @abstractmethod
    def enabled(self) -> bool:
        """Whether this executor actually attempts execution."""
        ...

    @abstractmethod
    def execute(self, request: SqlExecutionRequest) -> SqlExecutionResult:
        """Execute or dry-run SQL and return a structured result."""
        ...
