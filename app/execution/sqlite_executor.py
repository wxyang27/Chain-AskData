"""SQLite executor for optional local demos."""

import re
import sqlite3
import time
from pathlib import Path

from app.execution.base import SqlExecutor
from app.execution.objects import SqlExecutionRequest, SqlExecutionResult


class SQLiteSqlExecutor(SqlExecutor):
    def __init__(self, db_path: str):
        self.db_path = db_path

    @property
    def mode(self) -> str:
        return "sqlite"

    @property
    def enabled(self) -> bool:
        return True

    def execute(self, request: SqlExecutionRequest) -> SqlExecutionResult:
        t0 = time.perf_counter()
        sql = request.sql or ""
        db_file = Path(self.db_path)
        if not db_file.exists():
            return self._failed(request, f"sqlite_db_not_found: {db_file}", t0)

        stripped = sql.strip()
        if not (stripped.upper().startswith("SELECT") or stripped.upper().startswith("WITH")):
            return self._failed(request, "only SELECT and WITH statements can be executed", t0)
        if re.search(r"\b(INSERT|UPDATE|DELETE|DROP|TRUNCATE|ALTER|CREATE)\b", stripped, re.I):
            return self._failed(request, "write_or_ddl_statement_rejected", t0)

        try:
            with sqlite3.connect(str(db_file), timeout=request.timeout_seconds) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(sql)
                rows = cursor.fetchmany(request.max_rows)
                columns = [desc[0] for desc in cursor.description or []]
                sample_rows = [dict(row) for row in rows[:3]]
                return SqlExecutionResult(
                    enabled=True,
                    mode=self.mode,
                    status="success",
                    database=request.database,
                    sql=sql,
                    columns=columns,
                    sample_rows=sample_rows,
                    row_count=len(rows),
                    execution_ms=self._elapsed_ms(t0),
                    dry_run=False,
                )
        except Exception as exc:
            return self._failed(request, f"sqlite_execution_failed: {exc}", t0)

    def _failed(self, request: SqlExecutionRequest, error: str, t0: float) -> SqlExecutionResult:
        return SqlExecutionResult(
            enabled=True,
            mode=self.mode,
            status="failed",
            database=request.database,
            sql=request.sql,
            error=error,
            execution_ms=self._elapsed_ms(t0),
            dry_run=False,
        )

    def _elapsed_ms(self, t0: float) -> int:
        return int((time.perf_counter() - t0) * 1000)
