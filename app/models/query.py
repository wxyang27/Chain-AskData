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


class CoTSemantics(BaseModel):
    """LLM 对用户问题的语义理解，内嵌于 QueryPlanCoT。

    一次 Qwen 调用同时输出 query_semantics + steps，
    不需要额外链路或模块。
    """

    metrics: list[str] = Field(default_factory=list)
    time_type: str = ""
    dimensions: list[str] = Field(default_factory=list)
    filters: list[str] = Field(default_factory=list)
    top_n: int | None = None


class SemanticContract(BaseModel):
    """Lightweight business semantics normalized from the user question.

    This is intentionally thin: it captures hard business constraints that
    should guide retrieval, planning, SQL generation, and static repair.
    """

    intent: str = "nl2sql"
    domain: str = ""
    metrics: list[str] = Field(default_factory=list)
    dimensions: list[str] = Field(default_factory=list)
    filters: list[str] = Field(default_factory=list)
    time_range: str = ""
    required_fields: list[str] = Field(default_factory=list)
    reject_reason: str = ""
    template_id: str = ""


class QueryPlanCoT(BaseModel):
    """Structured QueryPlan CoT step - AskData four-tuple format.

    Aligned with AskData reference design:
    (database, processing_objects, operation_instructions, output_target)

    processing_objects lists all involved table.field entries and join relations
    (e.g. "trade_summary.total_trade_count",
          "trade_summary.user_id <-> interest_info.user_id").

    operation_instructions describes the chain of execution in order:
    ["先筛选...", "再关联...", "然后聚合...", "最后输出..."].
    """

    step: int
    database: str = ""
    processing_objects: list[str] = Field(default_factory=list)
    operation_instructions: list[str] = Field(default_factory=list)
    output_target: str = ""
    evidence: list[str] = Field(default_factory=list)
    query_semantics: CoTSemantics = Field(default_factory=CoTSemantics)

    # --- backward-compatibility aliases (deprecated, prefer new names) ---

    @property
    def objects(self) -> list[str]:
        """Deprecated alias: extract table names from processing_objects."""
        table_names: list[str] = []
        for obj in self.processing_objects:
            if "<->" in obj:
                continue
            if "." in obj:
                table_names.append(obj.rsplit(".", 1)[0])
            else:
                table_names.append(obj)
        return list(dict.fromkeys(table_names))

    @property
    def fields(self) -> list[str]:
        """Deprecated: extract field names from processing_objects."""
        result = []
        for obj in self.processing_objects:
            if "<->" in obj:
                continue
            if "." in obj:
                result.append(obj.rsplit(".", 1)[-1])
            else:
                result.append(obj)
        return list(dict.fromkeys(result))

    @property
    def filters(self) -> list[str]:
        """Deprecated: first operation_instruction typically holds filters."""
        if self.operation_instructions:
            return [self.operation_instructions[0]]
        return []

    @property
    def calculation(self) -> str:
        """Deprecated: aggregation part from operation_instructions."""
        for instr in self.operation_instructions:
            if "聚合" in instr or "SUM" in instr or "COUNT" in instr:
                return instr
        return ""

    @property
    def output(self) -> str:
        """Deprecated alias for output_target."""
        return self.output_target


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
    query_plan_cot: list[QueryPlanCoT] = Field(default_factory=list)
    llm_enabled: bool = False
    llm_adopted: bool = False
    llm_model: str = ""
    llm_fallback_reason: str = ""
    llm_validation_passed: bool = False
    llm_validation_errors: list[str] = Field(default_factory=list)
    llm_latency_ms: int = 0
    llm_repair_count: int = 0
    semantic_contract: SemanticContract = Field(default_factory=SemanticContract)


class ValidationResult(BaseModel):
    """SQL 校验结果。"""

    passed: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class LlmSqlValidation(BaseModel):
    """LLM SQL 安全门禁校验结果。"""

    passed: bool = False
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    used_tables: list[str] = Field(default_factory=list)
    used_fields: list[str] = Field(default_factory=list)


class LlmSqlResult(BaseModel):
    """LLM SQL 生成结果（影子模式）。"""

    sql: str = ""
    used_tables: list[str] = Field(default_factory=list)
    used_fields: list[str] = Field(default_factory=list)
    explanation: str = ""
    generated: bool = False
    error: str = ""


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
    schema_graph: dict[str, Any] = Field(default_factory=dict)

    # --- LLM SQL shadow mode ---
    template_sql: str = ""
    llm_sql: str = ""
    llm_sql_adopted: bool = False
    llm_sql_validation: LlmSqlValidation = Field(default_factory=LlmSqlValidation)
    llm_sql_detail: LlmSqlResult = Field(default_factory=LlmSqlResult)
    sql_source: str = "template"
