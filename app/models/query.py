from typing import Any

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    """自然语言取数请求。"""

    question: str = Field(..., min_length=1, description="用户自然语言问题")


class MetricPlan(BaseModel):
    """QueryPlan 中的指标描述。"""

    canonical: str
    display_name: str
    formula: str


class DimensionPlan(BaseModel):
    """QueryPlan 中的维度描述。"""

    field: str
    alias: str
    source_table: str


class QueryPlan(BaseModel):
    """查询计划。

    MVP 阶段先用确定性 QueryPlan 代替模型 CoT，既能解释生成路径，也能做规则校验。
    RAG 增强阶段会记录被采纳的检索证据。
    """

    intent: str
    business_domain: str
    original_question: str = ""
    case_id: str = ""
    template_id: str = ""
    sql_strategy: str = "template_first"
    time_range: str = ""
    metrics: list[MetricPlan]
    dimensions: list[DimensionPlan] = Field(default_factory=list)
    filters: list[str] = Field(default_factory=list)
    source_tables: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    retrieved_metric_ids: list[str] = Field(default_factory=list)
    retrieved_field_names: list[str] = Field(default_factory=list)
    retrieved_table_names: list[str] = Field(default_factory=list)
    retrieved_example_ids: list[str] = Field(default_factory=list)
    planning_evidence: list[str] = Field(default_factory=list)
    schema_evidence: list[str] = Field(default_factory=list)


class ValidationResult(BaseModel):
    """SQL 校验结果。"""

    passed: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class QueryResponse(BaseModel):
    """自然语言取数响应。"""

    project: str
    question_summary: str
    query_plan: QueryPlan
    sql: str
    validation: ValidationResult
    caliber_notes: list[str]
    retrieval_trace: list[dict[str, Any]] = Field(default_factory=list)
    retrieval_context: dict[str, Any] = Field(default_factory=dict)
