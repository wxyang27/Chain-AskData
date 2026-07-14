"""Map validation failures to repair/fallback advice."""

from dataclasses import dataclass, field
from typing import Any

from app.execution.objects import SqlExecutionResult
from app.feedback.result_validator import ResultValidationResult


@dataclass
class RepairAdvice:
    """Decision support for repair_attempt stage."""

    needed: bool
    reason: str = ""
    categories: list[str] = field(default_factory=list)
    suggested_actions: list[str] = field(default_factory=list)
    fallback_to_template: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "needed": self.needed,
            "reason": self.reason,
            "categories": self.categories,
            "suggested_actions": self.suggested_actions,
            "fallback_to_template": self.fallback_to_template,
        }


class RepairPolicy:
    """Classify result/safety failures into deterministic repair actions."""

    def advise(
        self,
        *,
        execution_result: SqlExecutionResult,
        result_validation: ResultValidationResult,
        safety_errors: list[str],
        sql_source: str,
    ) -> RepairAdvice:
        if result_validation.status == "skipped":
            return RepairAdvice(needed=False, reason="execution_skipped")

        categories = self._categories(
            execution_result=execution_result,
            result_validation=result_validation,
            safety_errors=safety_errors,
        )
        if not categories:
            return RepairAdvice(needed=False, reason="no_feedback_issue")

        actions: list[str] = []
        if "unknown_field" in categories:
            actions.append("run_static_repair_against_schema_graph")
        if "date_function_error" in categories:
            actions.append("rewrite_non_maxcompute_date_functions")
        if "empty_result" in categories:
            actions.append("fallback_to_template_or_relax_high_risk_filters")
        if "missing_columns" in categories:
            actions.append("fallback_to_template_with_expected_aliases")
        if "all_null_metric" in categories:
            actions.append("fallback_to_template_or_check_metric_formula")
        if "execution_failed" in categories:
            actions.append("retry_after_static_repair")

        return RepairAdvice(
            needed=True,
            reason=";".join(categories),
            categories=categories,
            suggested_actions=list(dict.fromkeys(actions)),
            fallback_to_template=sql_source != "template" or "empty_result" in categories,
        )

    def _categories(
        self,
        *,
        execution_result: SqlExecutionResult,
        result_validation: ResultValidationResult,
        safety_errors: list[str],
    ) -> list[str]:
        categories: list[str] = []
        joined = " | ".join(
            safety_errors + result_validation.errors + [execution_result.error or ""]
        ).lower()

        if execution_result.status not in {"success", "skipped"}:
            categories.append("execution_failed")
        if "unknown_field" in joined or "unknown column" in joined or "no such column" in joined:
            categories.append("unknown_field")
        if "date_trunc" in joined or "dateadd" in joined or "mc_syntax" in joined:
            categories.append("date_function_error")
        if "empty_result" in joined:
            categories.append("empty_result")
        if "missing_expected_columns" in joined:
            categories.append("missing_columns")
        if "all_null_metric_columns" in joined:
            categories.append("all_null_metric")
        if "top_query_missing_order_by_limit" in joined:
            categories.append("top_query_shape")

        return list(dict.fromkeys(categories))
