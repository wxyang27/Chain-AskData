"""Deterministic static SQL repair for common business-caliber misses."""

import re
from dataclasses import dataclass, field

from app.models.query import SemanticContract
from app.schema_graph.graph import SchemaGraph


@dataclass
class SqlRepairResult:
    sql: str
    repaired: bool = False
    fixes: list[str] = field(default_factory=list)


class StaticSqlRepairer:
    """Patch small, deterministic SQL defects before falling back to templates."""

    EXEC_TABLE = "dm_opt_qy_user_execution_record_all_d"
    ORDER_TABLE = "dm_opt_qy_order_info_all_d"

    def repair(
        self,
        *,
        sql: str,
        semantic_contract: SemanticContract,
        schema_graph: SchemaGraph,
        errors: list[str],
    ) -> SqlRepairResult:
        if not sql.strip():
            return SqlRepairResult(sql=sql)

        if self._needs_dual_domain_sql(semantic_contract, schema_graph):
            return SqlRepairResult(
                sql=self._dual_domain_sql(semantic_contract),
                repaired=True,
                fixes=["rewrite_dual_payment_execution_metrics"],
            )

        repaired_sql = sql
        fixes: list[str] = []

        repaired_sql, fixed = self._repair_unverified_filter(repaired_sql, semantic_contract)
        if fixed:
            fixes.append("add_left_num_filter")

        repaired_sql, fixed = self._repair_payment_filters(repaired_sql, semantic_contract)
        if fixed:
            fixes.append("add_payment_filters")

        repaired_sql, fixed = self._repair_revenue_category_filter(repaired_sql, semantic_contract, schema_graph)
        if fixed:
            fixes.append("add_revenue_category_filter")

        repaired_sql, fixed = self._repair_channel_filter(repaired_sql, semantic_contract)
        if fixed:
            fixes.append("add_channel_filter")

        repaired_sql, fixed = self._repair_zero_income_order_count(repaired_sql, semantic_contract)
        if fixed:
            fixes.append("fix_zero_income_order_count")

        return SqlRepairResult(
            sql=repaired_sql,
            repaired=bool(fixes),
            fixes=fixes,
        )

    def _needs_dual_domain_sql(
        self,
        contract: SemanticContract,
        schema_graph: SchemaGraph,
    ) -> bool:
        return (
            "execution_income" in contract.metrics
            and "payment_gmv" in contract.metrics
            and self.EXEC_TABLE in schema_graph.table_names
            and self.ORDER_TABLE in schema_graph.table_names
        )

    def _dual_domain_sql(self, contract: SemanticContract) -> str:
        if contract.time_range == "this_month_mtd":
            execution_date = (
                "executed_date >= DATETRUNC(CURRENT_DATE(), 'MONTH') "
                "AND executed_date <= DATE_SUB(CURRENT_DATE(),1)"
            )
            pay_date = (
                "pay_date >= DATETRUNC(CURRENT_DATE(), 'MONTH') "
                "AND pay_date <= DATE_SUB(CURRENT_DATE(),1)"
            )
        elif contract.time_range == "yesterday":
            execution_date = "executed_date = DATE_SUB(CURRENT_DATE(),1)"
            pay_date = "pay_date = DATE_SUB(CURRENT_DATE(),1)"
        else:
            execution_date = (
                "executed_date >= DATE_SUB(CURRENT_DATE(),30) "
                "AND executed_date <= DATE_SUB(CURRENT_DATE(),1)"
            )
            pay_date = (
                "pay_date >= DATE_SUB(CURRENT_DATE(),30) "
                "AND pay_date <= DATE_SUB(CURRENT_DATE(),1)"
            )

        return f"""SELECT
  (SELECT SUM(exe_income)
   FROM soyoung_dw.dm_opt_qy_user_execution_record_all_d e
   WHERE e.dp = DATE_SUB(CURRENT_DATE(),1)
   AND e.is_valid = 1
   AND {self._qualify_date_condition(execution_date, "e")}) AS 核销收入,
  (SELECT SUM(pay_gmv)
   FROM soyoung_dw.dm_opt_qy_order_info_all_d p
   WHERE p.dp = DATE_SUB(CURRENT_DATE(),1)
   AND p.is_paydate_cash = 0
   AND {self._qualify_date_condition(pay_date, "p")}) AS 支付GMV"""

    def _qualify_date_condition(self, condition: str, alias: str) -> str:
        return (
            condition
            .replace("executed_date", f"{alias}.executed_date")
            .replace("pay_date", f"{alias}.pay_date")
        )

    def _repair_unverified_filter(
        self,
        sql: str,
        contract: SemanticContract,
    ) -> tuple[str, bool]:
        if "unverified_amount" not in contract.metrics:
            return sql, False
        if re.search(r"\bleft_num\s*>\s*0\b", sql, re.IGNORECASE):
            return sql, False

        alias = self._alias_for_table(sql, self.ORDER_TABLE)
        condition = f"{alias}.left_num > 0" if alias else "left_num > 0"
        return self._add_condition(sql, condition), True

    def _repair_payment_filters(
        self,
        sql: str,
        contract: SemanticContract,
    ) -> tuple[str, bool]:
        if not any(metric.startswith("payment_") for metric in contract.metrics):
            return sql, False

        repaired = sql
        changed = False
        alias = self._alias_for_table(sql, self.ORDER_TABLE)
        prefix = f"{alias}." if alias else ""

        if "is_paydate_cash = 0" not in re.sub(r"\s+", " ", repaired):
            repaired = self._add_condition(repaired, f"{prefix}is_paydate_cash = 0")
            changed = True

        if "is_pay_new = 1" in contract.filters and "is_pay_new = 1" not in re.sub(r"\s+", " ", repaired):
            repaired = self._add_condition(repaired, f"{prefix}is_pay_new = 1")
            changed = True

        if "pay_date" not in repaired and contract.time_range:
            repaired = self._add_condition(repaired, self._date_condition("pay_date", contract.time_range, prefix))
            changed = True

        return repaired, changed

    def _repair_revenue_category_filter(
        self,
        sql: str,
        contract: SemanticContract,
        schema_graph: SchemaGraph,
    ) -> tuple[str, bool]:
        category_filter = next(
            (item for item in contract.filters if item.startswith("revenue_category")),
            "",
        )
        if not category_filter:
            return sql, False
        if re.search(r"\brevenue_category\b\s*(?:=|IN\b|LIKE\b|REGEXP\b)", sql, re.IGNORECASE):
            return sql, False

        alias = self._alias_for_table(sql, self.EXEC_TABLE)
        condition = category_filter
        if alias:
            condition = condition.replace("revenue_category", f"{alias}.revenue_category")
        return self._add_condition(sql, condition), True

    def _repair_channel_filter(
        self,
        sql: str,
        contract: SemanticContract,
    ) -> tuple[str, bool]:
        channel_filter = next(
            (item for item in contract.filters if item.startswith("cx_first_channel =")),
            "",
        )
        if not channel_filter:
            return sql, False
        if self._condition_already_present(sql, channel_filter):
            return sql, False

        alias = self._alias_for_table(sql, self.EXEC_TABLE)
        condition = channel_filter
        if alias:
            condition = condition.replace("cx_first_channel", f"{alias}.cx_first_channel")

        # Replace broad channel comparison when the question asks for one channel.
        broad_channel = re.compile(
            r"(?:\w+\.)?cx_first_channel\s+IN\s*\(\s*'私域'\s*,\s*'公域'\s*,\s*'老带新'\s*\)",
            re.IGNORECASE,
        )
        if broad_channel.search(sql):
            return broad_channel.sub(condition, sql, count=1), True

        return self._add_condition(sql, condition), True

    def _repair_zero_income_order_count(
        self,
        sql: str,
        contract: SemanticContract,
    ) -> tuple[str, bool]:
        if "zero_income_order_count" not in contract.metrics:
            return sql, False
        if "main_order_id" in sql:
            return sql, False
        repaired = re.sub(
            r"COUNT\s*\(\s*\*\s*\)",
            "COUNT(DISTINCT main_order_id)",
            sql,
            count=1,
            flags=re.IGNORECASE,
        )
        return repaired, repaired != sql

    def _date_condition(self, field_name: str, time_range: str, prefix: str = "") -> str:
        field = f"{prefix}{field_name}"
        if time_range == "yesterday":
            return f"{field} = DATE_SUB(CURRENT_DATE(),1)"
        if time_range == "this_month_mtd":
            return (
                f"{field} >= DATETRUNC(CURRENT_DATE(), 'MONTH') "
                f"AND {field} <= DATE_SUB(CURRENT_DATE(),1)"
            )
        return (
            f"{field} >= DATE_SUB(CURRENT_DATE(),30) "
            f"AND {field} <= DATE_SUB(CURRENT_DATE(),1)"
        )

    def _alias_for_table(self, sql: str, table_name: str) -> str:
        pattern = re.compile(
            rf"(?:FROM|JOIN)\s+\w+\.{re.escape(table_name)}\s+(?:AS\s+)?(\w+)",
            re.IGNORECASE,
        )
        match = pattern.search(sql)
        if not match:
            return ""
        alias = match.group(1)
        if alias.upper() in {"WHERE", "ON", "GROUP", "ORDER", "LIMIT", "LEFT", "RIGHT", "INNER"}:
            return ""
        return alias

    def _add_condition(self, sql: str, condition: str) -> str:
        if not condition:
            return sql
        if self._condition_already_present(sql, condition):
            return sql

        stripped = sql.rstrip()
        semicolon = ";" if stripped.endswith(";") else ""
        if semicolon:
            stripped = stripped[:-1].rstrip()

        boundary = re.search(
            r"\b(GROUP\s+BY|ORDER\s+BY|HAVING|LIMIT)\b",
            stripped,
            re.IGNORECASE,
        )
        insert_at = boundary.start() if boundary else len(stripped)
        head = stripped[:insert_at].rstrip()
        tail = stripped[insert_at:].lstrip()

        if re.search(r"\bWHERE\b", head, re.IGNORECASE):
            head = f"{head}\nAND {condition}"
        else:
            head = f"{head}\nWHERE {condition}"

        return f"{head}\n{tail}".rstrip() + semicolon

    def _condition_already_present(self, sql: str, condition: str) -> bool:
        compact_sql = re.sub(r"\s+", "", sql).lower()
        compact_condition = re.sub(r"\s+", "", condition).lower()
        return compact_condition in compact_sql
