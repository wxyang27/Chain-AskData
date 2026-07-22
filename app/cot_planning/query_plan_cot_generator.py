import json
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any

from app.execution.capabilities import (
    CapabilityContext,
    create_default_capability_context,
)
from app.llm.local_client import LocalLLMClient
from app.llm.prompts import build_query_plan_cot_messages
from app.cot_planning.query_plan_cot_validator import QueryPlanCoTValidator
from app.models.query import CoTSemantics, QueryPlanCoT
from app.schema_graph.graph import SchemaGraph

MAX_REPAIR_ATTEMPTS = 1


@dataclass(frozen=True)
class LLMQueryPlanCoTResult:
    enabled: bool
    adopted: bool
    model: str
    steps: list[QueryPlanCoT] = field(default_factory=list)
    fallback_reason: str = ""
    raw_response: dict[str, Any] = field(default_factory=dict)
    validation_passed: bool = False
    validation_errors: list[str] = field(default_factory=list)
    latency_ms: int = 0
    repair_count: int = 0


class LLMQueryPlanCoTGenerator:
    """Generate QueryPlanCoT through local Qwen/OpenAI-compatible chat API.

    On validation failure the generator sends one repair request with
    specific error feedback before falling back to the rule-based CoT.
    """

    def __init__(
        self,
        *,
        enabled: bool = False,
        model: str = "qwen-thinking",
        timeout_seconds: int = 30,
        client: LocalLLMClient | None = None,
        validator: QueryPlanCoTValidator | None = None,
        capability_context: CapabilityContext | None = None,
        max_repairs: int = MAX_REPAIR_ATTEMPTS,
    ):
        self.enabled = enabled
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.client = client or LocalLLMClient()
        self.capability_context = capability_context or create_default_capability_context()
        self.validator = validator or QueryPlanCoTValidator(
            allowed_databases=self.capability_context.allowed_database_names()
        )
        self.max_repairs = max_repairs

    def generate(
        self,
        *,
        question: str,
        schema_graph: SchemaGraph | None,
        fallback_steps: list[QueryPlanCoT],
    ) -> LLMQueryPlanCoTResult:
        if not self.enabled:
            return LLMQueryPlanCoTResult(
                enabled=False,
                adopted=False,
                model=self.model,
                steps=fallback_steps,
                fallback_reason="llm_disabled",
            )
        if not schema_graph:
            return LLMQueryPlanCoTResult(
                enabled=True,
                adopted=False,
                model=self.model,
                steps=fallback_steps,
                fallback_reason="schema_graph_missing",
            )

        started_at = perf_counter()
        base_messages = build_query_plan_cot_messages(
            question=question,
            schema_graph_text=schema_graph.schema_graph_text,
            capability_context_text=self.capability_context.to_prompt_context(),
        )

        # --- first attempt ---
        try:
            payload = self.client.chat_json(
                model=self.model,
                messages=base_messages,
                temperature=0,
                timeout_seconds=self.timeout_seconds,
            )
            steps = self._parse_steps(payload)
        except Exception as exc:
            return LLMQueryPlanCoTResult(
                enabled=True,
                adopted=False,
                model=self.model,
                steps=fallback_steps,
                fallback_reason=str(exc),
                latency_ms=self._elapsed_ms(started_at),
            )

        validation = self.validator.validate(steps, schema_graph)
        repair_count = 0

        # --- repair loop ---
        while not validation.passed and repair_count < self.max_repairs:
            repair_messages = self._build_repair_messages(
                base_messages=base_messages,
                failed_payload=payload,
                errors=validation.errors,
            )
            repair_count += 1

            try:
                payload = self.client.chat_json(
                    model=self.model,
                    messages=repair_messages,
                    temperature=0,
                    timeout_seconds=self.timeout_seconds,
                )
                steps = self._parse_steps(payload)
            except Exception:
                break  # repair call failed, fall through to fallback

            validation = self.validator.validate(steps, schema_graph)

        # --- result ---
        if not validation.passed:
            return LLMQueryPlanCoTResult(
                enabled=True,
                adopted=False,
                model=self.model,
                steps=fallback_steps,
                fallback_reason="query_plan_cot_validation_failed",
                raw_response=payload,
                validation_passed=False,
                validation_errors=validation.errors,
                latency_ms=self._elapsed_ms(started_at),
                repair_count=repair_count,
            )

        return LLMQueryPlanCoTResult(
            enabled=True,
            adopted=True,
            model=self.model,
            steps=steps,
            raw_response=payload,
            validation_passed=True,
            latency_ms=self._elapsed_ms(started_at),
            repair_count=repair_count,
        )

    # ------------------------------------------------------------------
    # internal helpers
    # ------------------------------------------------------------------

    def _build_repair_messages(
        self,
        *,
        base_messages: list[dict[str, str]],
        failed_payload: dict[str, Any],
        errors: list[str],
    ) -> list[dict[str, str]]:
        error_list = "\n".join(f"- {e}" for e in errors)
        repair_prompt = (
            "你的上一次输出有以下校验错误，请根据 SchemaGraph 修正后重新输出正确的 JSON：\n\n"
            f"{error_list}\n\n"
            "要求：\n"
            "1. 只使用 SchemaGraph 中存在的表、字段和关联关系\n"
            "2. operation_instructions 按链式步骤描述（先筛选、再关联、然后聚合、最后输出）\n"
            "3. 仅输出符合指定结构的 JSON object"
        )

        return [
            *base_messages,
            {"role": "assistant", "content": json.dumps(failed_payload, ensure_ascii=False)},
            {"role": "user", "content": repair_prompt},
        ]

    def _parse_steps(self, payload: dict[str, Any]) -> list[QueryPlanCoT]:
        raw_steps = payload.get("steps")
        if not isinstance(raw_steps, list) or not raw_steps:
            raise ValueError("LLM JSON must include non-empty steps list")

        # Parse query_semantics from payload root
        semantics = self._parse_semantics(payload.get("query_semantics"))

        steps = []
        for index, raw_step in enumerate(raw_steps, start=1):
            if not isinstance(raw_step, dict):
                raise ValueError("Each LLM step must be an object")
            # Attach semantics to first step
            step_semantics = semantics if index == 1 else CoTSemantics()
            steps.append(
                QueryPlanCoT(
                    step=int(raw_step.get("step") or index),
                    database=str(
                        raw_step.get("database")
                        or self.capability_context.default_database_name()
                    ),
                    processing_objects=self._as_string_list(
                        raw_step.get("processing_objects")
                    ),
                    operation_instructions=self._as_string_list(
                        raw_step.get("operation_instructions")
                    ),
                    output_target=str(raw_step.get("output_target") or ""),
                    evidence=self._as_string_list(raw_step.get("evidence")),
                    query_semantics=step_semantics,
                )
            )

        if not any(step.processing_objects for step in steps):
            raise ValueError("LLM steps must include processing_objects")
        if not any(step.operation_instructions for step in steps):
            raise ValueError("LLM steps must include operation_instructions")
        return steps

    def _parse_semantics(self, raw: Any) -> CoTSemantics:
        if not isinstance(raw, dict):
            return CoTSemantics()
        return CoTSemantics(
            metrics=self._as_string_list(raw.get("metrics")),
            time_type=str(raw.get("time_type") or ""),
            dimensions=self._as_string_list(raw.get("dimensions")),
            filters=self._as_string_list(raw.get("filters")),
            top_n=raw.get("top_n") if isinstance(raw.get("top_n"), int) else None,
        )

    def _as_string_list(self, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item) for item in value if str(item).strip()]
        if isinstance(value, str) and value.strip():
            return [value]
        return []

    def _elapsed_ms(self, started_at: float) -> int:
        return max(0, round((perf_counter() - started_at) * 1000))
