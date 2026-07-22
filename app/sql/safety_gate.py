"""SQL safety and caliber gate for LLM-generated SQL.

Validates MaxCompute SQL against SchemaGraph constraints and caliber rules.
Failing validation continues to return template SQL (gate is advisory).
"""

import re
from dataclasses import dataclass, field
from typing import Any

from app.schema_graph.graph import SchemaGraph

_NAMED_CITY_TERMS = (
    "\u5317\u4eac",
    "\u5317\u4eac\u5e02",
    "\u4e0a\u6d77",
    "\u4e0a\u6d77\u5e02",
    "\u5e7f\u5dde",
    "\u5e7f\u5dde\u5e02",
    "\u6df1\u5733",
    "\u6df1\u5733\u5e02",
    "\u6b66\u6c49",
    "\u6b66\u6c49\u5e02",
    "\u676d\u5dde",
    "\u676d\u5dde\u5e02",
    "\u6210\u90fd",
    "\u6210\u90fd\u5e02",
    "\u91cd\u5e86",
    "\u91cd\u5e86\u5e02",
    "\u5929\u6d25",
    "\u5929\u6d25\u5e02",
    "\u5357\u4eac",
    "\u5357\u4eac\u5e02",
    "\u82cf\u5dde",
    "\u82cf\u5dde\u5e02",
    "\u897f\u5b89",
    "\u897f\u5b89\u5e02",
    "\u90d1\u5dde",
    "\u90d1\u5dde\u5e02",
    "\u957f\u6c99",
    "\u957f\u6c99\u5e02",
    "\u9752\u5c9b",
    "\u9752\u5c9b\u5e02",
    "\u5b81\u6ce2",
    "\u5b81\u6ce2\u5e02",
    "\u5408\u80a5",
    "\u5408\u80a5\u5e02",
    "\u4f5b\u5c71",
    "\u4f5b\u5c71\u5e02",
    "\u4e1c\u839e",
    "\u4e1c\u839e\u5e02",
)
_STORE_ALIAS = "\u95e8\u5e97"
_THIS_MONTH_TERMS = ("\u672c\u6708", "\u8fd9\u4e2a\u6708", "\u5f53\u6708")
_NAMED_ITEM_TERMS = (
    "\u5947\u8ff9\u80f6\u539f",
    "BBL HERO",
    "\u5947\u8ff9\u7ae5\u989c",
    "\u70ed\u739b\u5409",
)


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

        # 5. Every snapshot table (_d suffix) must have dp = yesterday.
        # Business date windows must use executed_date/pay_date/etc.  The dp
        # partition on current full snapshot / all_d tables is the data-version
        # partition and must not be ranged.
        snapshot_tables = [t for t in tables if t.endswith("_d")]
        if snapshot_tables:
            aliases = self._extract_aliases(sql)
            for table in snapshot_tables:
                dp_status = self._validate_snapshot_dp_filter(
                    sql=sql,
                    table=table,
                    table_alias=aliases.get(table, ""),
                    allow_bare_dp=len(snapshot_tables) == 1,
                )
                if dp_status == "missing":
                    errors.append(f"missing_dp_filter:{table}")
                elif dp_status == "range":
                    errors.append(
                        f"invalid_dp_filter:{table}:dp_must_equal_yesterday_not_range"
                    )
                elif dp_status == "not_yesterday":
                    errors.append(
                        f"invalid_dp_filter:{table}:dp_must_equal_DATE_SUB_CURRENT_DATE_1"
                    )

        # 6. Execution queries must have is_valid and executed_date
        has_execution_table = any(
            "execution_record" in t for t in tables
        )
        if has_execution_table:
            if not re.search(r"\bis_valid\s*=\s*1\b", sql):
                errors.append("missing_is_valid_filter")
            if not re.search(r"\bexecuted_date\b", sql):
                errors.append("missing_executed_date_filter")

        # 7. Dimension semantics implied by the natural language query.
        self._validate_dimension_semantics(sql, schema_graph, errors)
        self._validate_business_semantics(sql, schema_graph, errors)

        # 8. ORDER BY must have LIMIT
        if "ORDER BY" in sql_upper and "LIMIT" not in sql_upper:
            errors.append("order_by_without_limit")
        self._validate_top_n_semantics(sql, schema_graph, errors)

        # 9. Division without NULLIF guard
        div_pattern = re.compile(
            r"(\w+)\s*/\s*(?!NULLIF)(?!0\b)(?![\d.]+)(\w+)", re.I
        )
        for match in div_pattern.finditer(sql):
            denominator = match.group(2)
            if denominator.upper() in ("NULLIF", "CAST", "CASE"):
                continue
            errors.append(f"division_without_nullif:{match.group(0).strip()[:40]}")

        # 10. Penetration rate: must use REGEXP or LIKE for item filter
        if "standard_name" in sql and ("渗透率" in sql or "penetration" in sql.lower()):
            if not re.search(r"standard_name\s+(?:REGEXP|LIKE)\s+", sql):
                errors.append("item_penetration_missing_regexp")

        # 11. Pay-to-verify rate: must use CTE (WITH) or DATE_ADD
        if ("main_order_id" in sql and "pay_date" in sql and "executed_date" in sql
                and ("核销率" in sql or "verify_rate" in sql.lower() or "30日" in sql)):
            if "WITH" not in sql_upper and "DATE_ADD" not in sql_upper:
                errors.append("pay_verify_rate_missing_cte_or_dateadd")
            if "NULLIF" not in sql_upper:
                errors.append("pay_verify_rate_missing_nullif_rate")

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

    def _validate_snapshot_dp_filter(
        self,
        *,
        sql: str,
        table: str,
        table_alias: str,
        allow_bare_dp: bool,
    ) -> str:
        """Validate a snapshot table partition predicate.

        Returns:
        - "ok" when dp is exactly yesterday
        - "missing" when no dp predicate is present for the table
        - "range" when dp uses a range/non-equality operator
        - "not_yesterday" when dp uses equality but not yesterday
        """
        qualifiers = [q for q in (table_alias, table) if q]
        if allow_bare_dp:
            qualifiers.append("")

        predicates: list[tuple[str, str]] = []
        for qualifier in dict.fromkeys(qualifiers):
            predicates.extend(self._dp_predicates(sql, qualifier))

        if not predicates:
            return "missing"

        if any(op.upper() != "=" for op, _ in predicates):
            return "range"

        if any(self._is_yesterday_partition(value) for _, value in predicates):
            return "ok"
        return "not_yesterday"

    def _dp_predicates(self, sql: str, qualifier: str) -> list[tuple[str, str]]:
        """Extract dp predicates for a table alias/table name or bare dp."""
        if qualifier:
            left = rf"{re.escape(qualifier)}\.dp"
        else:
            left = r"(?<!\.)\bdp"

        pattern = re.compile(
            rf"\b{left}\b\s*(=|>=|<=|<>|!=|>|<|BETWEEN|IN)\s*"
            rf"(.+?)(?=\s+(?:AND|OR|GROUP\s+BY|ORDER\s+BY|HAVING|LIMIT|JOIN|WHERE|ON)\b|[;\n]|$)",
            re.IGNORECASE | re.DOTALL,
        )
        return [
            (match.group(1), match.group(2).strip())
            for match in pattern.finditer(sql)
        ]

    def _is_yesterday_partition(self, value: str) -> bool:
        compact = re.sub(r"\s+", "", value).upper().rstrip(";")
        return compact in {
            "DATE_SUB(CURRENT_DATE(),1)",
            "CURRENT_DATE()-1",
        }

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

    def _validate_dimension_semantics(
        self,
        sql: str,
        schema_graph: SchemaGraph,
        errors: list[str],
    ) -> None:
        city_roots = self._named_city_roots(schema_graph.query)
        if city_roots:
            if not self._has_city_filter(sql):
                errors.append("missing_city_filter:city_name")
            elif not self._has_city_fuzzy_filter(sql):
                errors.append("city_filter_should_use_regexp_or_like:city_name")
            elif not any(root in sql for root in city_roots):
                errors.append("city_filter_value_mismatch:city_name")

        if re.search(
            rf"\b(?:\w+\.)?standard_name\b\s+AS\s+[`\"']?{_STORE_ALIAS}",
            sql,
            re.IGNORECASE,
        ):
            errors.append("alias_semantics:standard_name_is_item_not_store")

        item_roots = self._named_item_roots(schema_graph.query)
        if item_roots:
            if not self._has_item_filter(sql):
                errors.append("missing_item_filter:standard_name")
            elif not self._has_item_fuzzy_filter(sql):
                errors.append("item_filter_should_use_regexp_or_like:standard_name")
            elif not any(root in sql for root in item_roots):
                errors.append("item_filter_value_mismatch:standard_name")

        required_dimensions = self._required_group_dimensions(schema_graph.query)
        sql_upper = sql.upper()
        for dimension_name, field_name in required_dimensions.items():
            field_upper = field_name.upper()
            if not re.search(rf"\b(?:\w+\.)?{field_upper}\b", sql_upper):
                errors.append(f"missing_dimension:{dimension_name}:{field_name}")
                continue
            if (
                self._has_aggregate(sql)
                and not re.search(rf"GROUP\s+BY[\s\S]+(?:\w+\.)?{field_upper}\b", sql_upper)
            ):
                errors.append(f"missing_group_by_dimension:{dimension_name}:{field_name}")

    def _named_city_roots(self, query: str) -> set[str]:
        roots: set[str] = set()
        for term in _NAMED_CITY_TERMS:
            if term in query:
                roots.add(term.removesuffix("\u5e02"))
        return roots

    def _named_item_roots(self, query: str) -> set[str]:
        return {term for term in _NAMED_ITEM_TERMS if term in query}

    def _has_city_filter(self, sql: str) -> bool:
        return bool(
            re.search(
                r"\b(?:\w+\.)?city_name\b\s*(?:=|IN\b|LIKE\b|REGEXP\b|RLIKE\b)",
                sql,
                re.IGNORECASE,
            )
        )

    def _has_city_fuzzy_filter(self, sql: str) -> bool:
        return bool(
            re.search(
                r"\b(?:\w+\.)?city_name\b\s*(?:LIKE\b|REGEXP\b|RLIKE\b)",
                sql,
                re.IGNORECASE,
            )
        )

    def _has_item_filter(self, sql: str) -> bool:
        return bool(
            re.search(
                r"\b(?:\w+\.)?standard_name\b\s*(?:=|IN\b|LIKE\b|REGEXP\b|RLIKE\b)",
                sql,
                re.IGNORECASE,
            )
        )

    def _has_item_fuzzy_filter(self, sql: str) -> bool:
        return bool(
            re.search(
                r"\b(?:\w+\.)?standard_name\b\s*(?:LIKE\b|REGEXP\b|RLIKE\b)",
                sql,
                re.IGNORECASE,
            )
        )

    def _required_group_dimensions(self, query: str) -> dict[str, str]:
        rules = {
            "\u54c1\u9879": ("standard_name", ("\u5404\u54c1\u9879", "\u6309\u54c1\u9879", "\u54c1\u9879TOP", "\u54c1\u9879\u6392\u884c")),
            "\u54c1\u7c7b": ("revenue_category", ("\u5404\u54c1\u7c7b", "\u6309\u54c1\u7c7b", "\u54c1\u7c7b\u5360\u6bd4", "\u54c1\u7c7b\u5bf9\u6bd4")),
            "\u95e8\u5e97": ("sy_hospital_name", ("\u5404\u95e8\u5e97", "\u6309\u95e8\u5e97", "\u95e8\u5e97TOP", "\u95e8\u5e97\u6392\u884c")),
            "\u57ce\u5e02": ("city_name", ("\u5404\u57ce\u5e02", "\u6309\u57ce\u5e02", "\u5206\u57ce\u5e02", "\u57ce\u5e02\u5bf9\u6bd4")),
            "\u6e20\u9053": ("cx_first_channel", ("\u5404\u6e20\u9053", "\u6309\u6e20\u9053", "\u5206\u6e20\u9053", "\u6e20\u9053\u5bf9\u6bd4")),
            "\u65b0\u8001\u5ba2": ("is_new", ("\u65b0\u8001\u5ba2", "\u65b0\u5ba2\u548c\u8001\u5ba2", "\u65b0\u5ba2\u8001\u5ba2")),
        }
        required: dict[str, str] = {}
        for dimension_name, (field_name, triggers) in rules.items():
            if any(trigger in query for trigger in triggers):
                required[dimension_name] = field_name
        return required

    def _has_aggregate(self, sql: str) -> bool:
        return bool(re.search(r"\b(SUM|COUNT|AVG|MIN|MAX)\s*\(", sql, re.IGNORECASE))

    def _validate_business_semantics(
        self,
        sql: str,
        schema_graph: SchemaGraph,
        errors: list[str],
    ) -> None:
        query = schema_graph.query or ""
        upper_sql = sql.upper()

        if any(term in query for term in ("待核销", "没核销", "未核销")):
            if "DM_OPT_QY_ORDER_INFO_ALL_D" not in upper_sql:
                errors.append("business_semantics:unverified_must_use_order_info")
            if not re.search(r"\bleft_num\s*>\s*0\b", sql, re.IGNORECASE):
                errors.append("business_semantics:missing_left_num_filter")
            if re.search(r"\b(pay_date|executed_date)\b", sql, re.IGNORECASE):
                errors.append("business_semantics:unverified_should_not_use_business_date")

        if self._query_has_payment_metric(query):
            if "DM_OPT_QY_ORDER_INFO_ALL_D" not in upper_sql:
                errors.append("business_semantics:payment_must_use_order_info")
            if not re.search(r"\bis_paydate_cash\s*=\s*0\b", sql, re.IGNORECASE):
                errors.append("business_semantics:missing_is_paydate_cash_filter")
            if not re.search(r"\bpay_date\b", sql, re.IGNORECASE):
                errors.append("business_semantics:missing_pay_date_filter")
            if "新客" in query and not re.search(r"\bis_pay_new\s*=\s*1\b", sql, re.IGNORECASE):
                errors.append("business_semantics:missing_is_pay_new_filter")

        if self._query_requests_time_progress_achievement(query):
            if "DIM_CHANNEL_MONTH_INCOME_TARGET" not in upper_sql:
                errors.append("business_semantics:progress_must_use_target_table")
            if "TARGET_ABSOLUTE_VALUE" not in upper_sql:
                errors.append("business_semantics:progress_missing_target_value")
            if not re.search(r"\btarget_type\b\s*=\s*'收入'", sql, re.IGNORECASE):
                errors.append("business_semantics:progress_missing_income_target_type")
            if not re.search(r"\bsecond_level_hierarchy\b\s*=\s*'大单品'", sql, re.IGNORECASE):
                errors.append("business_semantics:progress_missing_big_item_level")
            if "TIME_PROGRESS_ACHIEVEMENT_RATE" not in upper_sql:
                errors.append("business_semantics:progress_missing_achievement_output")

        if any(term in query for term in ("大单品", "常规品", "大师团")):
            if not re.search(
                r"\brevenue_category\b\s*(?:=|IN\b|LIKE\b|REGEXP\b|RLIKE\b)",
                sql,
                re.IGNORECASE,
            ):
                errors.append("business_semantics:missing_revenue_category_filter")

        if any(term in query for term in ("0元单", "0 元单", "0元核销", "0 元核销")):
            if not re.search(r"\bexe_income\s*=\s*0\b", sql, re.IGNORECASE):
                errors.append("business_semantics:missing_zero_income_filter")
            if not re.search(
                r"COUNT\s*\(\s*DISTINCT\s+(?:\w+\.)?main_order_id\s*\)",
                sql,
                re.IGNORECASE,
            ):
                errors.append("business_semantics:zero_income_orders_must_count_main_order_id")

        if "人次占比" in query or ("占比" in query and "人次" in query):
            if not re.search(r"/\s*NULLIF\s*\(", sql, re.IGNORECASE):
                errors.append("business_semantics:missing_visit_ratio_nullif")
            if not re.search(
                r"COUNT\s*\(\s*DISTINCT\s+(?:\w+\.)?verify_date_id\s*\)",
                sql,
                re.IGNORECASE,
            ):
                errors.append("business_semantics:missing_total_visit_denominator")

        if "私域" in query and not all(term in query for term in ("私域", "公域", "老带新")):
            if not re.search(
                r"\bcx_first_channel\b\s*=\s*'私域'",
                sql,
                re.IGNORECASE,
            ):
                errors.append("business_semantics:missing_private_channel_filter")

    def _validate_top_n_semantics(
        self,
        sql: str,
        schema_graph: SchemaGraph,
        errors: list[str],
    ) -> None:
        top_n = self._query_top_n(schema_graph.query or "")
        if top_n is None:
            return

        limit_match = re.search(r"\bLIMIT\s+(\d+)", sql, re.IGNORECASE)
        if not limit_match:
            errors.append(f"top_n_semantics:missing_limit:{top_n}")
            return

        actual_limit = int(limit_match.group(1))
        if actual_limit != top_n:
            errors.append(
                f"top_n_semantics:limit_mismatch:expected_{top_n}_got_{actual_limit}"
            )

    def _query_top_n(self, query: str) -> int | None:
        match = re.search(r"(?i)top\s*(\d+)", query)
        if match:
            return int(match.group(1))
        match = re.search(r"前\s*(\d+)", query)
        if match:
            return int(match.group(1))
        return None

    def _query_has_payment_metric(self, query: str) -> bool:
        return any(
            term in query
            for term in ("支付GMV", "支付人数", "支付客单价", "付了多少", "多少人付", "人均", "按支付日")
        )

    def _query_requests_time_progress_achievement(self, query: str) -> bool:
        return (
            "核销收入" in query
            and any(term in query for term in ("时间进度", "进度达成率", "达成率", "进度完成率"))
        )

    def _cte_aliases(self, sql: str) -> set[str]:
        """Extract CTE alias names from WITH clauses."""
        aliases = set()
        cte_names = {
            m.group(1)
            for m in re.finditer(r"(?:\bWITH|,)\s+(\w+)\s+AS\s*\(", sql, re.IGNORECASE)
        }
        aliases.update(cte_names)

        reserved = {
            "ON", "WHERE", "AND", "OR", "GROUP", "ORDER", "HAVING", "LIMIT",
            "LEFT", "RIGHT", "INNER", "OUTER", "JOIN",
        }
        for cte_name in cte_names:
            pattern = rf"(?:FROM|JOIN)\s+{re.escape(cte_name)}\s+(?:AS\s+)?(\w+)"
            for match in re.finditer(pattern, sql, re.IGNORECASE):
                alias = match.group(1)
                if alias.upper() not in reserved:
                    aliases.add(alias)
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

        compact_sql = re.sub(r"\s+", "", sql).upper()
        for business_date_field in ("EXECUTED_DATE", "PAY_DATE"):
            if re.search(
                rf"(?:\w+\.)?{business_date_field}<=CURRENT_DATE\(\)",
                compact_sql,
            ):
                errors.append(
                    f"date_semantics:{business_date_field.lower()}_end_must_be_yesterday"
                )
            if re.search(
                rf"(?:\w+\.)?{business_date_field}BETWEEN.+ANDCURRENT_DATE\(\)",
                compact_sql,
            ):
                errors.append(
                    f"date_semantics:{business_date_field.lower()}_end_must_be_yesterday"
                )

        if self._query_requests_this_month_mtd(schema_graph.query):
            self._validate_this_month_mtd_window(compact_sql, errors)

        if "本周" not in schema_graph.query:
            return

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

    def _query_requests_this_month_mtd(self, query: str) -> bool:
        return any(term in query for term in _THIS_MONTH_TERMS)

    def _validate_this_month_mtd_window(
        self,
        compact_sql: str,
        errors: list[str],
    ) -> None:
        if "DATE_SUB(CURRENT_DATE(),30)" in compact_sql:
            errors.append("date_semantics:this_month_must_not_be_last_30d")

        business_fields = [
            field
            for field in ("EXECUTED_DATE", "PAY_DATE")
            if field in compact_sql
        ]
        if not business_fields:
            errors.append("date_semantics:this_month_missing_business_date")
            return

        month_start = (
            r"(?:DATETRUNC\(CURRENT_DATE\(\),['\"]?(?:MONTH|MON|MM)['\"]?\)"
            r"|DATE_FORMAT\(CAST\(CURRENT_DATE\(\)ASTIMESTAMP\),['\"]YYYY-MM-01['\"]\))"
        )
        yesterday = r"DATE_SUB\(CURRENT_DATE\(\),1\)"

        for field in business_fields:
            date_field = rf"(?:\w+\.)?{field}"
            has_month_start = bool(
                re.search(rf"{date_field}>={month_start}", compact_sql)
                or re.search(rf"{date_field}BETWEEN{month_start}AND", compact_sql)
            )
            has_yesterday_end = bool(
                re.search(rf"{date_field}<={yesterday}", compact_sql)
                or re.search(rf"{date_field}BETWEEN{month_start}AND{yesterday}", compact_sql)
            )

            if not has_month_start:
                errors.append(
                    f"date_semantics:this_month_start_must_be_month_first:{field.lower()}"
                )
            if not has_yesterday_end:
                errors.append(
                    f"date_semantics:this_month_end_must_be_yesterday:{field.lower()}"
                )
