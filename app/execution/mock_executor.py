"""Mock SQL executor for stable closed-loop demos.

The mock executor does not connect to a database.  It checks the statement
shape, infers output columns from the SELECT clause, and returns deterministic
sample rows so the API can demonstrate a full Text2SQL loop.
"""

import re
import time
from typing import Any

from app.execution.base import SqlExecutor
from app.execution.objects import SqlExecutionRequest, SqlExecutionResult


class MockSqlExecutor(SqlExecutor):
    @property
    def mode(self) -> str:
        return "mock"

    @property
    def enabled(self) -> bool:
        return True

    def execute(self, request: SqlExecutionRequest) -> SqlExecutionResult:
        t0 = time.perf_counter()
        sql = request.sql or ""
        stripped = sql.strip()
        if not stripped:
            return self._error(request, "empty_sql", t0)

        upper_sql = stripped.upper()
        if not (upper_sql.startswith("SELECT") or upper_sql.startswith("WITH")):
            return self._error(request, "only SELECT and WITH statements can be executed", t0)

        if re.search(r"\b(INSERT|UPDATE|DELETE|DROP|TRUNCATE|ALTER|CREATE)\b", upper_sql):
            return self._error(request, "write_or_ddl_statement_rejected", t0)

        columns = self._infer_columns(sql)
        limit_match = re.search(r"\bLIMIT\s+(\d+)\b", sql, re.I)
        row_count = min(int(limit_match.group(1)), request.max_rows) if limit_match else min(3, request.max_rows)
        row_count = max(row_count, 0)
        sample_count = min(row_count, 3)
        sample_rows = [
            {column: self._mock_value(column, row_idx) for column in columns}
            for row_idx in range(sample_count)
        ]

        return SqlExecutionResult(
            enabled=True,
            mode=self.mode,
            status="success",
            sql=sql,
            columns=columns,
            sample_rows=sample_rows,
            row_count=row_count,
            execution_ms=self._elapsed_ms(t0),
            dry_run=True,
        )

    def _error(self, request: SqlExecutionRequest, error: str, t0: float) -> SqlExecutionResult:
        return SqlExecutionResult(
            enabled=True,
            mode=self.mode,
            status="failed",
            sql=request.sql,
            error=error,
            execution_ms=self._elapsed_ms(t0),
            dry_run=True,
        )

    def _elapsed_ms(self, t0: float) -> int:
        return int((time.perf_counter() - t0) * 1000)

    def _infer_columns(self, sql: str) -> list[str]:
        select_match = re.search(
            r"\bSELECT\s+(.*?)\s+FROM\b",
            sql,
            re.I | re.S,
        )
        if not select_match:
            return ["result"]

        columns: list[str] = []
        for part in self._split_select(select_match.group(1)):
            column = self._infer_column_name(part)
            if column:
                columns.append(column)
        return columns or ["result"]

    def _infer_column_name(self, expression: str) -> str:
        part = expression.strip()
        alias_match = re.search(r"\bAS\s+[`'\"]?([^`'\"\s,]+)[`'\"]?\s*$", part, re.I)
        if alias_match:
            return alias_match.group(1)

        simple_alias = re.search(r"\s+([A-Za-z_][\w]*)\s*$", part)
        if simple_alias and "(" not in simple_alias.group(1):
            return simple_alias.group(1)

        field_match = re.search(r"(?:\b\w+\.)?([A-Za-z_][\w]*)\s*$", part)
        if field_match:
            return field_match.group(1)

        func_match = re.match(r"(\w+)\s*\(", part)
        if func_match:
            return func_match.group(1).lower()

        return f"col_{abs(hash(part)) % 1000}"

    def _split_select(self, text: str) -> list[str]:
        parts: list[str] = []
        depth = 0
        current: list[str] = []
        for ch in text:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth = max(depth - 1, 0)
            if ch == "," and depth == 0:
                parts.append("".join(current))
                current = []
            else:
                current.append(ch)
        if current:
            parts.append("".join(current))
        return parts

    def _mock_value(self, column: str, row_idx: int) -> Any:
        lower = column.lower()
        if any(term in lower for term in ("cnt", "count", "人数", "人次", "数量")):
            return 1000 + row_idx
        if any(term in lower for term in ("income", "gmv", "金额", "收入", "客单价")):
            return round(10000.0 + row_idx * 123.45, 2)
        return f"{column}_sample_{row_idx + 1}"
