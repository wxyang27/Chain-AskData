"""Lightweight validation for SQL execution results."""

import re
from dataclasses import dataclass, field
from typing import Any

from app.execution.objects import SqlExecutionResult
from app.models.query import QueryPlan


@dataclass
class ResultValidationResult:
    """Post-execution validation result."""

    passed: bool
    status: str = "passed"
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    expected_columns: list[str] = field(default_factory=list)
    actual_columns: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "status": self.status,
            "errors": self.errors,
            "warnings": self.warnings,
            "expected_columns": self.expected_columns,
            "actual_columns": self.actual_columns,
        }


class ResultValidator:
    """Validate execution feedback before the answer is finalized."""

    AMOUNT_TERMS = ("金额", "收入", "GMV", "gmv", "income", "amount", "客单价")
    COUNT_TERMS = ("人数", "人次", "数量", "订单数", "cnt", "count")

    def validate(
        self,
        *,
        sql: str,
        query_plan: QueryPlan,
        execution_result: SqlExecutionResult,
    ) -> ResultValidationResult:
        if not execution_result.enabled or execution_result.status == "skipped":
            return ResultValidationResult(
                passed=True,
                status="skipped",
                warnings=["execution_disabled; result validation skipped"],
            )

        errors: list[str] = []
        warnings: list[str] = []

        if execution_result.status != "success":
            errors.append(f"execution_failed:{execution_result.error or execution_result.status}")

        if execution_result.status == "success" and execution_result.row_count == 0:
            errors.append("empty_result")

        expected_columns = self._expected_columns(query_plan)
        actual_columns = execution_result.columns
        missing = self._missing_expected_columns(expected_columns, actual_columns)
        if missing:
            errors.append("missing_expected_columns:" + ",".join(missing))

        null_columns = self._all_null_metric_columns(execution_result.sample_rows)
        if null_columns:
            errors.append("all_null_metric_columns:" + ",".join(null_columns))

        if self._looks_like_top_query(query_plan, sql):
            upper_sql = sql.upper()
            if "ORDER BY" not in upper_sql or "LIMIT" not in upper_sql:
                errors.append("top_query_missing_order_by_limit")

        errors.extend(
            self._question_constraint_errors(
                sql=sql,
                question=query_plan.original_question or "",
                actual_columns=actual_columns,
            )
        )

        return ResultValidationResult(
            passed=not errors,
            status="passed" if not errors else "failed",
            errors=errors,
            warnings=warnings,
            expected_columns=expected_columns,
            actual_columns=actual_columns,
        )

    def _expected_columns(self, query_plan: QueryPlan) -> list[str]:
        columns: list[str] = []
        for dim in query_plan.dimensions:
            columns.append(dim.alias or dim.field)
        for metric in query_plan.metrics:
            columns.extend([metric.display_name, metric.canonical])
        return [item for item in dict.fromkeys(columns) if item]

    def _missing_expected_columns(
        self,
        expected_columns: list[str],
        actual_columns: list[str],
    ) -> list[str]:
        if not expected_columns or not actual_columns:
            return []

        normalized_actual = [self._normalize(col) for col in actual_columns]
        missing: list[str] = []
        for expected in expected_columns:
            aliases = self._column_aliases(expected)
            if not any(
                self._normalize(alias) in actual or actual in self._normalize(alias)
                for alias in aliases
                for actual in normalized_actual
            ):
                missing.append(expected)
        return missing

    def _column_aliases(self, column: str) -> list[str]:
        aliases = [column]
        lowered = column.lower()
        normalized = self._normalize(column)
        if (
            "syhospitalname" in normalized
            or "tenantname" in normalized
            or column in {"门店", "机构", "医院"}
        ):
            aliases.extend([
                "门店",
                "机构",
                "医院",
                "sy_hospital_name",
                "tenant_name",
                "tenant_alias_name",
                "hospital_name",
                "store_name",
            ])
        if "execution_income" in lowered:
            aliases.extend([
                "核销收入",
                "执行收入",
                "收入",
                "exe_income",
                "execution_income",
                "income",
                "total_income",
                "total_exe_income",
                "sum_exe_income",
                "revenue",
                "amount",
            ])
        if column in {"核销收入", "收入"} or normalized in {
            "income",
            "totalincome",
            "totalexeincome",
            "sumexeincome",
        }:
            aliases.extend([
                "核销收入",
                "exe_income",
                "execution_income",
                "income",
                "total_income",
                "total_exe_income",
                "sum_exe_income",
            ])
        if "payment_gmv" in lowered:
            aliases.extend(["支付GMV", "pay_gmv", "payment_gmv", "gmv", "total_gmv"])
        if "payment_user_count" in lowered:
            aliases.extend(["支付人数", "支付用户数", "uid", "user_count", "payment_user_count"])
        if "payment_aov" in lowered:
            aliases.extend(["支付客单价", "payment_aov", "aov"])
        if "execution_visit_count" in lowered:
            aliases.extend(["核销人次", "verify_date_id", "visit_count", "execution_visit_count"])
        if "execution_user_count" in lowered:
            aliases.extend(["核销人数", "customer_id", "user_count", "execution_user_count"])
        if "unverified_amount" in lowered:
            aliases.extend(["待核销金额", "left_gmv", "unverified_amount", "left_amount"])
        return aliases

    def _all_null_metric_columns(self, sample_rows: list[dict[str, Any]]) -> list[str]:
        if not sample_rows:
            return []
        columns = sample_rows[0].keys()
        null_columns: list[str] = []
        for column in columns:
            if not self._is_metric_like_column(column):
                continue
            values = [row.get(column) for row in sample_rows]
            if values and all(value is None for value in values):
                null_columns.append(column)
        return null_columns

    def _is_metric_like_column(self, column: str) -> bool:
        return any(term in column for term in self.AMOUNT_TERMS + self.COUNT_TERMS)

    def _looks_like_top_query(self, query_plan: QueryPlan, sql: str) -> bool:
        question = query_plan.original_question or ""
        return bool(
            re.search(r"\bTOP\s*\d+\b", question, re.I)
            or "top" in question.lower()
            or "排行" in question
            or "排名" in question
            or re.search(r"\bLIMIT\s+\d+\b", sql, re.I)
        )

    def _question_constraint_errors(
        self,
        *,
        sql: str,
        question: str,
        actual_columns: list[str],
    ) -> list[str]:
        errors: list[str] = []
        normalized_sql = self._normalize(sql)
        normalized_actual = [self._normalize(column) for column in actual_columns]

        if self._question_requests_store(question):
            has_store_column = any(
                any(
                    self._normalize(alias) in actual
                    or actual in self._normalize(alias)
                    for alias in self._column_aliases("门店")
                )
                for actual in normalized_actual
            )
            has_store_sql = "syhospitalname" in normalized_sql
            has_store_group = bool(
                re.search(r"group\s+by[\s\S]*(sy_hospital_name|门店)", sql, re.I)
            )
            if not (has_store_column or has_store_sql) or not has_store_group:
                errors.append("missing_question_dimension:store:sy_hospital_name")

        if self._question_requests_city(question) and "cityname" not in normalized_sql:
            errors.append("missing_question_filter:city_name")

        if self._question_requests_item(question) and "standardname" not in normalized_sql:
            errors.append("missing_question_filter:standard_name")

        top_n = self._question_top_n(question)
        if top_n is not None:
            match = re.search(r"\blimit\s+(\d+)\b", sql, re.I)
            if not match:
                errors.append(f"missing_question_top_n:limit_{top_n}")
            elif int(match.group(1)) != top_n:
                errors.append(f"top_n_mismatch:expected_{top_n}:actual_{match.group(1)}")

        return errors

    def _question_requests_store(self, question: str) -> bool:
        return any(term in question for term in ("门店", "各店", "店铺", "机构", "医院"))

    def _question_requests_city(self, question: str) -> bool:
        return any(
            city in question
            for city in (
                "北京", "上海", "广州", "深圳", "武汉", "杭州", "成都", "重庆",
                "天津", "南京", "苏州", "西安", "郑州", "长沙", "青岛", "宁波",
                "合肥", "佛山", "东莞",
            )
        )

    def _question_requests_item(self, question: str) -> bool:
        return any(item in question for item in ("奇迹胶原", "BBL HERO", "奇迹童颜", "热玛吉"))

    def _question_top_n(self, question: str) -> int | None:
        match = re.search(r"\btop\s*(\d+)\b", question, re.I)
        if match:
            return int(match.group(1))
        return None

    def _normalize(self, text: str) -> str:
        return re.sub(r"[\s_`'\".]+", "", str(text)).lower()
