"""MaxCompute SQL executor backed by PyODPS.

The executor is intentionally read-only. It mirrors the target project's
``mcp_router`` idea, but keeps the Chain-AskData execution layer interface:
disabled/mock/sqlite/maxcompute can be swapped without changing the pipeline.
"""

from __future__ import annotations

import re
from time import perf_counter
from typing import Any

from app.core.config import settings
from app.execution.base import SqlExecutor
from app.execution.objects import SqlExecutionRequest, SqlExecutionResult


_FORBIDDEN_SQL = re.compile(
    r"\b(insert|update|delete|create|drop|alter|truncate|merge|grant|revoke|"
    r"overwrite|set\s+odps\.sql\.submit\.mode)\b",
    re.IGNORECASE,
)


class MaxComputeSqlExecutor(SqlExecutor):
    """Read-only MaxCompute executor using ``odps.ODPS.execute_sql``."""

    def __init__(
        self,
        *,
        access_id: str | None = None,
        secret_access_key: str | None = None,
        project: str | None = None,
        endpoint: str | None = None,
    ):
        self.access_id = settings.odps_access_id if access_id is None else access_id
        self.secret_access_key = (
            settings.odps_secret_access_key
            if secret_access_key is None
            else secret_access_key
        )
        self.project = settings.odps_project_name if project is None else project
        self.endpoint = settings.odps_endpoint if endpoint is None else endpoint

    @property
    def mode(self) -> str:
        return "maxcompute"

    @property
    def enabled(self) -> bool:
        return True

    def execute(self, request: SqlExecutionRequest) -> SqlExecutionResult:
        start = perf_counter()
        sql = self._normalize_sql(request.sql)

        if request.database and request.database != self.project:
            return self._failed(
                request,
                sql,
                (
                    "maxcompute_database_not_registered: "
                    f"{request.database} is not registered for this executor"
                ),
                start,
            )

        if not self._has_credentials():
            return self._failed(
                request,
                sql,
                "maxcompute_not_configured: missing ODPS_ACCESS_ID or ODPS_SECRET_ACCESS_KEY",
                start,
                dry_run=True,
            )

        if not self._is_readonly_sql(sql):
            return self._failed(
                request,
                sql,
                "maxcompute_readonly_violation: only SELECT/WITH queries are allowed",
                start,
            )

        try:
            from odps import ODPS  # type: ignore
        except Exception as exc:
            return self._failed(
                request,
                sql,
                f"pyodps_not_installed: {exc}",
                start,
                dry_run=True,
            )

        try:
            odps_client = ODPS(
                self.access_id,
                self.secret_access_key,
                self.project,
                endpoint=self.endpoint,
            )
            instance = odps_client.execute_sql(self._limit_sql(sql, request.max_rows))
            rows, columns = self._read_instance(instance, request.max_rows)
            return SqlExecutionResult(
                enabled=True,
                mode=self.mode,
                status="success",
                database=request.database,
                sql=sql,
                columns=columns,
                sample_rows=rows,
                row_count=len(rows),
                execution_ms=self._elapsed_ms(start),
                dry_run=False,
            )
        except Exception as exc:
            return self._failed(request, sql, str(exc), start)

    def _has_credentials(self) -> bool:
        return bool(self.access_id.strip() and self.secret_access_key.strip())

    def _is_readonly_sql(self, sql: str) -> bool:
        compact = re.sub(r"\s+", " ", sql.strip()).lower()
        if not (compact.startswith("select ") or compact.startswith("with ")):
            return False
        return not _FORBIDDEN_SQL.search(compact)

    def _normalize_sql(self, sql: str) -> str:
        return sql.strip().rstrip(";")

    def _limit_sql(self, sql: str, max_rows: int) -> str:
        if max_rows <= 0:
            return sql
        if re.search(r"\blimit\s+\d+\s*$", sql, flags=re.IGNORECASE):
            return sql
        return f"{sql}\nLIMIT {max_rows}"

    def _read_instance(self, instance: Any, max_rows: int) -> tuple[list[dict[str, Any]], list[str]]:
        rows: list[dict[str, Any]] = []
        columns: list[str] = []

        with instance.open_reader(tunnel=False) as reader:
            schema = getattr(reader, "schema", None)
            if schema is not None:
                names = getattr(schema, "names", None)
                if names:
                    columns = list(names)

            for idx, record in enumerate(reader):
                if idx >= max_rows:
                    break
                row = self._record_to_dict(record, columns)
                if not columns:
                    columns = list(row.keys())
                rows.append(row)

        return rows, columns

    def _record_to_dict(self, record: Any, columns: list[str]) -> dict[str, Any]:
        if hasattr(record, "asdict"):
            return dict(record.asdict())
        try:
            pairs = list(record)
            if pairs and all(isinstance(item, tuple) and len(item) == 2 for item in pairs):
                return {str(name): value for name, value in pairs}
        except Exception:
            pass
        if columns:
            return {column: record[column] for column in columns}
        if isinstance(record, dict):
            return dict(record)
        values = list(record) if not isinstance(record, str) else [record]
        return {f"col_{idx + 1}": value for idx, value in enumerate(values)}

    def _failed(
        self,
        request: SqlExecutionRequest,
        sql: str,
        error: str,
        start: float,
        *,
        dry_run: bool = False,
    ) -> SqlExecutionResult:
        return SqlExecutionResult(
            enabled=True,
            mode=self.mode,
            status="failed",
            database=request.database,
            sql=sql or request.sql,
            error=error,
            execution_ms=self._elapsed_ms(start),
            dry_run=dry_run,
        )

    def _elapsed_ms(self, start: float) -> int:
        return int((perf_counter() - start) * 1000)
