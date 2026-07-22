"""Factory for execution-mode selection."""

from app.core.config import settings
from app.execution.base import SqlExecutor
from app.execution.maxcompute_executor import MaxComputeSqlExecutor
from app.execution.mock_executor import MockSqlExecutor
from app.execution.objects import SqlExecutionRequest, SqlExecutionResult
from app.execution.sqlite_executor import SQLiteSqlExecutor


class DisabledSqlExecutor(SqlExecutor):
    @property
    def mode(self) -> str:
        return "disabled"

    @property
    def enabled(self) -> bool:
        return False

    def execute(self, request: SqlExecutionRequest) -> SqlExecutionResult:
        return SqlExecutionResult(
            enabled=False,
            mode=self.mode,
            status="skipped",
            database=request.database,
            sql=request.sql,
            error="execution_disabled",
            dry_run=True,
        )


def create_sql_executor(mode: str | None = None) -> SqlExecutor:
    selected = (mode or settings.execution_mode or "disabled").strip().lower()
    if selected == "disabled":
        return DisabledSqlExecutor()
    if selected == "mock":
        return MockSqlExecutor()
    if selected == "sqlite":
        return SQLiteSqlExecutor(settings.execution_sqlite_path)
    if selected in {"maxcompute", "odps"}:
        return MaxComputeSqlExecutor()
    return DisabledSqlExecutor()
