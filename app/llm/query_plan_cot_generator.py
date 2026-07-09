from dataclasses import dataclass, field
from time import perf_counter
from typing import Any

from app.llm.local_client import LocalLLMClient
from app.llm.prompts import build_query_plan_cot_messages
from app.llm.query_plan_cot_validator import QueryPlanCoTValidator
from app.models.query import QueryPlanCoT
from app.schema_graph.graph import SchemaGraph


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
    """Generate QueryPlanCoT through local Qwen/OpenAI-compatible chat API."""

    def __init__(
        self,
        *,
        enabled: bool = False,
        model: str = "qwen-thinking",
        timeout_seconds: int = 30,
        client: LocalLLMClient | None = None,
        validator: QueryPlanCoTValidator | None = None,
    ):
        self.enabled = enabled
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.client = client or LocalLLMClient()
        self.validator = validator or QueryPlanCoTValidator()

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
        try:
            payload = self.client.chat_json(
                model=self.model,
                messages=build_query_plan_cot_messages(
                    question=question,
                    schema_graph_text=schema_graph.schema_graph_text,
                ),
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
            )

        return LLMQueryPlanCoTResult(
            enabled=True,
            adopted=True,
            model=self.model,
            steps=steps,
            raw_response=payload,
            validation_passed=True,
            latency_ms=self._elapsed_ms(started_at),
        )

    def _parse_steps(self, payload: dict[str, Any]) -> list[QueryPlanCoT]:
        raw_steps = payload.get("steps")
        if not isinstance(raw_steps, list) or not raw_steps:
            raise ValueError("LLM JSON must include non-empty steps list")

        steps = []
        for index, raw_step in enumerate(raw_steps, start=1):
            if not isinstance(raw_step, dict):
                raise ValueError("Each LLM step must be an object")
            steps.append(
                QueryPlanCoT(
                    step=int(raw_step.get("step") or index),
                    database=str(raw_step.get("database") or "soyoung_dw"),
                    processing_objects=self._as_string_list(
                        raw_step.get("processing_objects")
                    ),
                    operation_instructions=self._as_string_list(
                        raw_step.get("operation_instructions")
                    ),
                    output_target=str(raw_step.get("output_target") or ""),
                    evidence=self._as_string_list(raw_step.get("evidence")),
                )
            )

        if not any(step.processing_objects for step in steps):
            raise ValueError("LLM steps must include processing_objects")
        if not any(step.operation_instructions for step in steps):
            raise ValueError("LLM steps must include operation_instructions")
        return steps

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
