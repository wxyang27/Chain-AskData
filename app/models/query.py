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
    """查询计划。"""

    intent: str
    business_domain: str
    metrics: list[MetricPlan]
    dimensions: list[DimensionPlan] = Field(default_factory=list)
    filters: list[str] = Field(default_factory=list)
    source_tables: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)


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
