"""Lightweight dataclasses for Pipeline trace and run result."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PipelineStageLog:
    """Observability record for a single pipeline stage."""

    name: str
    status: str = "ok"
    summary: str = ""
    inputs: dict[str, Any] = field(default_factory=dict)
    outputs: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    latency_ms: int = 0


@dataclass
class PipelineTrace:
    """End-to-end trace across all pipeline stages."""

    question: str
    stages: list[PipelineStageLog] = field(default_factory=list)
    final_sql_source: str = ""
    final_intent: str = ""
    final_template_id: str = ""

    def add_stage(self, stage: PipelineStageLog) -> None:
        self.stages.append(stage)

    def to_dict(self) -> dict[str, Any]:
        return {
            "question": self.question,
            "final_sql_source": self.final_sql_source,
            "final_intent": self.final_intent,
            "final_template_id": self.final_template_id,
            "stages": [
                {
                    "name": s.name,
                    "status": s.status,
                    "summary": s.summary,
                    "errors": s.errors,
                    "latency_ms": s.latency_ms,
                }
                for s in self.stages
            ],
        }


@dataclass
class PipelineRunResult:
    """Complete result of a pipeline run.

    Carries all intermediate artifacts so AnswerComposer can
    assemble the final QueryResponse without re-running stages.
    """

    question: str
    retrieval_context: Any = None
    semantic_contract: Any = None
    intent_route: Any = None
    schema_result: dict[str, Any] = field(default_factory=dict)
    schema_graph: Any = None
    query_plan: Any = None
    template_sql: str = ""
    llm_sql: str = ""
    final_sql: str = ""
    sql_source: str = ""
    validation: Any = None
    llm_sql_validation: Any = None
    llm_sql_detail: Any = None
    template_id: str = ""
    trace: PipelineTrace | None = None
