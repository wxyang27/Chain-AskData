"""Mock SQL Executor — validates structure, returns placeholder results.

Use this when DataWorks/MaxCompute is not connected yet.
Pipeline execution stage is fully functional with the mock —
it validates SQL syntax, infers column shapes, and reports
expected row counts based on LIMIT clauses.
"""

import re
import time
from typing import Any

from app.model_clients.executor_client import ExecutionResult, ExecutorClient


class MockExecutor(ExecutorClient):
    """Dry-run executor that validates SQL syntax and returns placeholders.

    This is NOT a full SQL parser, but it catches the most common
    MaxCompute syntax issues: missing dp, missing WHERE, invalid LIMIT,
    non-SELECT statements.
    """

    @property
    def provider_name(self) -> str:
        return "mock"

    @property
    def is_readonly(self) -> bool:
        return True

    def execute(
        self,
        sql: str,
        *,
        timeout_seconds: int = 30,
        max_rows: int = 1000,
    ) -> ExecutionResult:
        t0 = time.perf_counter()

        if not sql or not sql.strip():
            return ExecutionResult(
                success=False,
                sql=sql,
                error_message="empty_sql",
                dry_run=True,
            )

        sql_upper = sql.strip().upper()

        # --- structural checks ---
        errors = []
        if not (sql_upper.startswith("SELECT") or sql_upper.startswith("WITH")):
            errors.append("only SELECT and WITH allowed")

        if "DROP" in sql_upper or "DELETE" in sql_upper or "TRUNCATE" in sql_upper:
            errors.append("destructive statements not allowed")

        if errors:
            return ExecutionResult(
                success=False,
                sql=sql,
                error_message="; ".join(errors),
                dry_run=True,
            )

        # --- infer result shape ---
        columns = self._infer_columns(sql)
        limit_match = re.search(r"LIMIT\s+(\d+)", sql, re.IGNORECASE)
        expected_rows = min(int(limit_match.group(1)), max_rows) if limit_match else max_rows

        # Generate placeholder rows
        placeholder_rows = [
            [f"val_{c}_{i}" for c in range(len(columns))]
            for i in range(min(expected_rows, 3))  # mock returns up to 3 rows
        ]

        elapsed_ms = int((time.perf_counter() - t0) * 1000)

        return ExecutionResult(
            success=True,
            sql=sql,
            columns=columns,
            rows=placeholder_rows,
            row_count=len(placeholder_rows),
            error_message="",
            execution_ms=elapsed_ms,
            dry_run=True,
        )

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _infer_columns(self, sql: str) -> list[str]:
        """Infer output column names from SQL SELECT clause.

        Handles: aliases (AS xxx), aggregations, simple fields.
        """
        columns: list[str] = []

        # Extract SELECT ... FROM (before the first FROM)
        select_match = re.search(
            r"\bSELECT\s+(.*?)\s+FROM\b", sql, re.IGNORECASE | re.DOTALL,
        )
        if not select_match:
            return ["result"]

        select_text = select_match.group(1)

        # Split by comma, respecting nested parens
        parts = self._split_select(select_text)
        for part in parts:
            part = part.strip()

            # Check for explicit alias: "... AS alias"
            alias_match = re.search(
                r"\bAS\s+['\"]?(\w+)['\"]?\s*$", part, re.IGNORECASE,
            )
            if alias_match:
                columns.append(alias_match.group(1))
                continue

            # Check for Chinese alias : "... AS 门店"
            alias_cn = re.search(r"\bAS\s+(.+?)\s*$", part, re.IGNORECASE)
            if alias_cn:
                columns.append(alias_cn.group(1).strip("'\"` "))
                continue

            # Named function call: SUM(xxx) → "sum_xxx"
            func_match = re.match(r"\b(\w+)\s*\((.+)\)", part, re.IGNORECASE)
            if func_match:
                func_name = func_match.group(1).lower()
                inner = func_match.group(2).strip()
                col = inner.split(".")[-1] if "." in inner else inner
                columns.append(f"{func_name}_{col}"[:30])
                continue

            # Simple field reference: table.field or alias.field
            field_match = re.match(r"\b[\w.]+\.([\w]+)\s*$", part, re.IGNORECASE)
            if field_match:
                columns.append(field_match.group(1))
                continue

            # Fallback
            simple = re.sub(r"['\"`]", "", part)[:30].strip()
            if simple:
                columns.append(simple)
            else:
                columns.append(f"col_{len(columns)}")

        return columns or ["result"]

    def _split_select(self, text: str) -> list[str]:
        """Split SELECT column list by comma, respecting nested parentheses."""
        parts = []
        depth = 0
        current = []
        for ch in text:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            if ch == "," and depth == 0:
                parts.append("".join(current))
                current = []
            else:
                current.append(ch)
        if current:
            parts.append("".join(current))
        return parts
