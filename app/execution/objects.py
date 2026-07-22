"""Dataclasses for SQL execution requests and results."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SqlExecutionRequest:
    """Request passed from the pipeline to an executor."""

    sql: str
    database: str = "soyoung_dw"
    mode: str = "disabled"
    timeout_seconds: int = 30
    max_rows: int = 100


@dataclass
class SqlExecutionResult:
    """Structured execution result surfaced by API and pipeline trace."""

    enabled: bool
    mode: str
    status: str
    database: str = "soyoung_dw"
    sql: str = ""
    columns: list[str] = field(default_factory=list)
    sample_rows: list[dict[str, Any]] = field(default_factory=list)
    row_count: int = 0
    error: str = ""
    execution_ms: int = 0
    dry_run: bool = True

    @property
    def success(self) -> bool:
        return self.status == "success"

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "enabled": self.enabled,
            "mode": self.mode,
            "status": self.status,
            "database": self.database,
            "sql": self.sql,
            "columns": self.columns,
            "sample_rows": self.sample_rows,
            "row_count": self.row_count,
            "error": self.error,
            "error_message": self.error,
            "execution_ms": self.execution_ms,
            "dry_run": self.dry_run,
        }
