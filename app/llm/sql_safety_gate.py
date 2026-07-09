"""SQL safety and caliber gate for LLM-generated SQL.

Validates MaxCompute SQL against SchemaGraph constraints and caliber rules.
Failing validation continues to return template SQL (gate is advisory).
"""

import re
from dataclasses import dataclass, field
from typing import Any

from app.schema_graph.graph import SchemaGraph


@dataclass
class SqlSafetyResult:
    passed: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    used_tables: list[str] = field(default_factory=list)
    used_fields: list[str] = field(default_factory=list)


class SqlSafetyGate:
    """Validate LLM SQL against safety and caliber rules."""

    def validate(
        self,
        sql: str,
        schema_graph: SchemaGraph,
    ) -> SqlSafetyResult:
        errors: list[str] = []
        warnings: list[str] = []

        if not sql or not sql.strip():
            return SqlSafetyResult(passed=False, errors=["empty_sql"])

        sql_upper = sql.upper().strip()

        # 1. Only SELECT / WITH allowed
        if not (sql_upper.startswith("SELECT") or sql_upper.startswith("WITH")):
            errors.append("forbidden_statement: only SELECT and WITH are allowed")

        # 2. Extract table references
        tables = self._extract_tables(sql)
        fields = self._extract_fields(sql)

        # 2. Forbidden non-MaxCompute syntax
        FORBIDDEN_PATTERNS = [
            (r"\bDATE_TRUNC\b", "DATE_TRUNC is not supported in MaxCompute"),
            (r"\bINTERVAL\s+\d+\s+(DAY|MONTH|YEAR|HOUR|MINUTE|SECOND)",
             "INTERVAL arithmetic not supported in MaxCompute"),
            (r"\bDATEADD\b", "Use DATE_ADD instead of DATEADD"),
            (r"\bDATEDIFF\b", "Use DATEDIFF with care; prefer DATE_SUB for ranges"),
            (r"\bSTR_TO_DATE\b", "STR_TO_DATE not supported in MaxCompute"),
            (r"\bNOW\(\)", "Use CURRENT_DATE() instead of NOW()"),
            (r"\bGETDATE\(\)", "Use CURRENT_DATE() instead of GETDATE()"),
        ]
        for pattern, msg in FORBIDDEN_PATTERNS:
            if re.search(pattern, sql, re.IGNORECASE):
                errors.append(f"mc_syntax:{msg}")
                break  # One syntax error is enough to flag

        # Date functions must be syntactically valid and match query semantics.
        self._validate_date_semantics(sql, schema_graph, errors)

        # 3. Tables must exist in SchemaGraph
        allowed_tables = {
            t.get("table_name") or ""
            for t in schema_graph.tables
        }
        for table in tables:
            if table not in allowed_tables:
                errors.append(f"unknown_table:{table}")

        # 4. Fields must exist in SchemaGraph
        allowed_fields = self._allowed_field_names(schema_graph)
        cte_aliases = self._cte_aliases(sql)
        for field in fields:
            prefix = field.split(".", 1)[0] if "." in field else ""
            if prefix in cte_aliases:
                continue  # CTE-internal alias, not a schema field
            if field not in allowed_fields:
                field_name = field.rsplit(".", 1)[-1] if "." in field else field
                if not any(f.endswith(f".{field_name}") for f in allowed_fields):
                    errors.append(f"unknown_field:{field}")

        # 5. Every snapshot table (_d suffix) must have dp filter
        snapshot_tables = [t for t in tables if t.endswith("_d")]
        if snapshot_tables:
            aliases = self._extract_aliases(sql)
            DP_OPS = r"(?:=|>=|<=|>|<|BETWEEN|IN|<>|!=)"
            for table in snapshot_tables:
                table_alias = aliases.get(table, "")
                dp_ok = (
                    (table_alias and re.search(
                        rf"{re.escape(table_alias)}\.dp\s*{DP_OPS}", sql, re.I))
                    or re.search(rf"{re.escape(table)}\.dp\s*{DP_OPS}", sql, re.I)
                    or bool(re.search(rf"\bdp\s*{DP_OPS}", sql, re.I))
                )
                if not dp_ok:
                    errors.append(f"missing_dp_filter:{table}")

        # 6. Execution queries must have is_valid and executed_date
        has_execution_table = any(
            "execution_record" in t for t in tables
        )
        if has_execution_table:
            if not re.search(r"\bis_valid\s*=\s*1\b", sql):
                errors.append("missing_is_valid_filter")
            if not re.search(r"\bexecuted_date\b", sql):
                errors.append("missing_executed_date_filter")

        # 7. ORDER BY must have LIMIT
        if "ORDER BY" in sql_upper and "LIMIT" not in sql_upper:
            errors.append("order_by_without_limit")

        # 8. Division without NULLIF guard
        div_pattern = re.compile(
            r"(\w+)\s*/\s*(?!NULLIF)(?!0\b)(?![\d.]+)(\w+)", re.I
        )
        for match in div_pattern.finditer(sql):
            denominator = match.group(2)
            if denominator.upper() in ("NULLIF", "CAST", "CASE"):
                continue
            errors.append(f"division_without_nullif:{match.group(0).strip()[:40]}")

        return SqlSafetyResult(
            passed=not errors,
            errors=errors,
            warnings=warnings,
            used_tables=tables,
            used_fields=fields,
        )

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _extract_tables(self, sql: str) -> list[str]:
        """Extract table names from FROM/JOIN clauses."""
        tables: list[str] = []
        # Match "db.table_name" or "db.table_name alias"
        pattern = r"(?:FROM|JOIN)\s+(\w+)\.(\w+)"
        for match in re.finditer(pattern, sql, re.IGNORECASE):
            db = match.group(1)
            table = match.group(2)
            tables.append(table)
        return list(dict.fromkeys(tables))

    def _extract_fields(self, sql: str) -> list[str]:
        """Extract alias.field references from SQL (not db.table in FROM/JOIN)."""
        fields: list[str] = []
        pattern = r"\b(\w+)\.(\w+)\b"

        # Skip purely numeric tokens like "1.0" or "100.field"
        def _is_numeric(s):
            try:
                float(s)
                return True
            except ValueError:
                return False

        from_ranges = []
        for m in re.finditer(
            r"(?:FROM|JOIN)\s+(\w+)\.(\w+)",
            sql, re.IGNORECASE,
        ):
            from_ranges.append((m.start(), m.end()))

        for match in re.finditer(pattern, sql):
            prefix = match.group(1)
            field = match.group(2)

            if _is_numeric(prefix) or _is_numeric(field):
                continue

            if prefix.upper() in ("DATE", "CURRENT", "CASE", "CAST", "NULLIF",
                                   "CONCAT", "COALESCE", "COUNT", "SUM", "AVG",
                                   "MAX", "MIN", "DISTINCT", "NOT", "AND", "OR",
                                   "STRING", "BIGINT", "INT", "DOUBLE", "DECIMAL"):
                continue

            if prefix == "soyoung_dw":
                continue

            pos = match.start()
            if any(start <= pos < end for start, end in from_ranges):
                continue

            fields.append(f"{prefix}.{field}")
        return list(dict.fromkeys(fields))

    def _extract_aliases(self, sql: str) -> dict[str, str]:
        """Extract table aliases from FROM/JOIN clauses.

        Returns dict mapping table_name -> alias.
        """
        aliases: dict[str, str] = {}
        # "FROM db.table alias" or "JOIN db.table alias"
        pattern = r"(?:FROM|JOIN)\s+\w+\.(\w+)\s+(?:AS\s+)?(\w+)"
        for match in re.finditer(pattern, sql, re.IGNORECASE):
            table = match.group(1)
            alias = match.group(2)
            if alias.upper() not in ("ON", "WHERE", "AND", "OR", "GROUP",
                                      "ORDER", "HAVING", "LIMIT", "LEFT",
                                      "RIGHT", "INNER", "OUTER", "CROSS"):
                aliases[table] = alias

        # Also handle "FROM db.table" without alias (table name is the alias)
        no_alias_pattern = r"(?:FROM|JOIN)\s+\w+\.(\w+)\s+(?:ON|WHERE|$)"
        for match in re.finditer(no_alias_pattern, sql, re.IGNORECASE):
            table = match.group(1)
            if table not in aliases:
                aliases[table] = table

        return aliases

    def _allowed_field_names(self, schema_graph: SchemaGraph) -> set[str]:
        """Build set of allowed field references."""
        allowed = set()
        for f in schema_graph.fields:
            table = f.get("table_name", "")
            name = f.get("field_name", "")
            if table and name:
                allowed.add(f"{table}.{name}")
                db = f.get("database_name") or "soyoung_dw"
                allowed.add(f"{db}.{table}.{name}")
        return allowed

    def _cte_aliases(self, sql: str) -> set[str]:
        """Extract CTE alias names from WITH clauses."""
        aliases = set()
        for m in re.finditer(r"\bWITH\s+(\w+)\s+AS\s*\(", sql, re.IGNORECASE):
            aliases.add(m.group(1))
        return aliases

    def _validate_date_semantics(
        self,
        sql: str,
        schema_graph: SchemaGraph,
        errors: list[str],
    ) -> None:
        """Validate MaxCompute date function arity and business time windows."""
        for arguments in self._function_arguments(sql, "DATE_SUB"):
            if len(arguments) != 2:
                errors.append(
                    "date_semantics:date_sub_invalid_arity:"
                    f"expected_2_got_{len(arguments)}"
                )

        if "本周" not in schema_graph.query:
            return

        compact_sql = re.sub(r"\s+", "", sql).upper()
        date_field = r"(?:\w+\.)?EXECUTED_DATE"
        week_start = (
            r"DATE_SUB\(CURRENT_DATE\(\),"
            r"WEEKDAY\(CAST\(CURRENT_DATE\(\)ASDATETIME\)\)\)"
        )
        yesterday = r"DATE_SUB\(CURRENT_DATE\(\),1\)"

        has_monday_start = bool(
            re.search(
                rf"{date_field}(?:>=|BETWEEN){week_start}",
                compact_sql,
            )
        )
        has_yesterday_end = bool(
            re.search(rf"{date_field}<={yesterday}", compact_sql)
            or re.search(
                rf"{date_field}BETWEEN{week_start}AND{yesterday}",
                compact_sql,
            )
        )

        if not has_monday_start:
            errors.append("date_semantics:this_week_start_must_be_monday")
        if not has_yesterday_end:
            errors.append("date_semantics:this_week_end_must_be_yesterday")

    def _function_arguments(
        self,
        sql: str,
        function_name: str,
    ) -> list[list[str]]:
        """Return top-level arguments for each function call in SQL."""
        calls: list[list[str]] = []
        pattern = re.compile(rf"\b{re.escape(function_name)}\s*\(", re.I)

        for match in pattern.finditer(sql):
            arguments: list[str] = []
            current: list[str] = []
            depth = 1
            quote = ""
            index = match.end()

            while index < len(sql) and depth > 0:
                char = sql[index]

                if quote:
                    current.append(char)
                    if char == quote:
                        if index + 1 < len(sql) and sql[index + 1] == quote:
                            current.append(sql[index + 1])
                            index += 1
                        else:
                            quote = ""
                elif char in {"'", '"'}:
                    quote = char
                    current.append(char)
                elif char == "(":
                    depth += 1
                    current.append(char)
                elif char == ")":
                    depth -= 1
                    if depth > 0:
                        current.append(char)
                elif char == "," and depth == 1:
                    arguments.append("".join(current).strip())
                    current = []
                else:
                    current.append(char)

                index += 1

            if depth == 0:
                arguments.append("".join(current).strip())
                calls.append(arguments)

        return calls
