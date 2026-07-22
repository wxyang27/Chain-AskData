"""LLM-based SQL generator (shadow mode).

Generates MaxCompute SQL from a validated QueryPlanCoT + SchemaGraph.
Runs alongside template SQL but does NOT replace it yet.
"""

import json
from dataclasses import dataclass, field
from typing import Any

from app.llm.local_client import LocalLLMClient
from app.models.query import QueryPlanCoT, SemanticContract
from app.schema_graph.graph import SchemaGraph


SQL_GENERATION_SYSTEM_PROMPT = """你是 MaxCompute SQL 生成助手。

根据已校验的 QueryPlanCoT 四元组和 SchemaGraph，生成一条可执行的 MaxCompute SQL。

必须遵守：
1. 只使用 SchemaGraph 中出现的表、字段和关联关系。
2. 不得编造不存在的表、字段或 JOIN 条件。
3. database 是执行路由元信息，不是 SQL 生成决策。SQL 生成阶段不得切换、编造或解释数据库路由；只按 SchemaGraph 中给出的表名生成 SQL。
4. 必须逐条落实 QueryPlanCoT.operation_instructions 中的筛选、关联、聚合/计算、排序/截断和输出要求，不得遗漏用户点名的城市、门店、品项、渠道、新老客、时间范围和 TopN。
5. 每张日快照/全量快照表（表名以 _d 结尾，包括 _all_d）必须有且只能有 dp = DATE_SUB(CURRENT_DATE(),1)。每个表别名都必须有自己的 dp = DATE_SUB(CURRENT_DATE(),1) 条件。
   - dp 是数据版本分区，不是业务日期；业务日期范围只能写在 executed_date / pay_date 等业务日期字段上。
   - 严禁对 dp 使用 >=、<=、BETWEEN、IN 或 CURRENT_DATE()，严禁写 dp 区间。
6. 核销相关查询必须有 is_valid = 1 和 executed_date 日期范围。
7. ORDER BY 必须有 LIMIT。
8. 除法运算必须用 NULLIF(分母, 0) 防止除零错误。

MaxCompute 语法约束（严格禁止以下语法）：
- 禁止：DATE_TRUNC、INTERVAL、DATEADD、DATEDIFF、STR_TO_DATE、NOW()
- 日期运算只用：DATE_SUB、DATE_ADD、TO_DATE、DATETRUNC
- 日期字面量只用：DATE_SUB(CURRENT_DATE(), N) 和 CURRENT_DATE()
- DATE_SUB 只能使用两个参数：DATE_SUB(日期, 天数)
- “本周”固定表示本周一至昨天：
  executed_date >= DATE_SUB(CURRENT_DATE(), WEEKDAY(CAST(CURRENT_DATE() AS DATETIME)))
  AND executed_date <= DATE_SUB(CURRENT_DATE(), 1)
- 禁止把“本周”写成上周日至本周六，禁止日期上限包含今天或未来日期
- 禁止：MySQL/PostgreSQL 特有函数或语法
- CTE（WITH 子句）标准 SQL 语法可用

9. 只输出 JSON，不输出解释或隐藏思考过程。
"""


SQL_GENERATION_SYSTEM_PROMPT += """

Additional business semantic rules:
- If the question names a city such as 北京、上海、武汉、杭州, join dim_qy_tenant_info_all_d through tenant_id and filter dim_qy_tenant_info_all_d.city_name with REGEXP or LIKE, for example city_name REGEXP '杭州'. Do not use city_name = '杭州' because stored values may be '杭州市'.
- city_name and area_name live on dim_qy_tenant_info_all_d for execution/order fact-table analysis unless SchemaGraph gives a more specific trusted table.
- standard_name is an item/product dimension. Never alias standard_name as store; store display should use sy_hospital_name.
- If the question names an item such as 奇迹胶原, BBL HERO, 奇迹童颜, or 热玛吉, filter by standard_name with REGEXP or LIKE, for example standard_name REGEXP '奇迹童颜'. Do not use exact equality for named item filters.
- If the question explicitly compares 私域/公域/老带新, add cx_first_channel IN ('私域','公域','老带新') instead of grouping all channels.
- Business date windows for executed_date/pay_date must end at DATE_SUB(CURRENT_DATE(), 1). Never use executed_date <= CURRENT_DATE() or pay_date <= CURRENT_DATE().
- For 本月 / this_month_mtd, business date windows must start at DATETRUNC(CURRENT_DATE(), 'MONTH') and end at DATE_SUB(CURRENT_DATE(), 1). Never translate 本月 as the last 30 days.
- Short follow-ups that mention only a city/item/channel/time/TopN are already resolved into a complete question. Treat those values as hard filters, not optional grouping dimensions.
"""


@dataclass
class LLMSqlResult:
    sql: str = ""
    used_tables: list[str] = field(default_factory=list)
    used_fields: list[str] = field(default_factory=list)
    explanation: str = ""
    raw_response: dict[str, Any] = field(default_factory=dict)
    generated: bool = False
    error: str = ""


class LLMSqlGenerator:
    """Generate MaxCompute SQL through Qwen from QueryPlanCoT + SchemaGraph."""

    def __init__(
        self,
        *,
        enabled: bool = False,
        model: str = "qwen-plus",
        timeout_seconds: int = 60,
        client: LocalLLMClient | None = None,
    ):
        self.enabled = enabled
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.client = client or LocalLLMClient()

    def generate(
        self,
        *,
        cot_steps: list[QueryPlanCoT],
        schema_graph: SchemaGraph | None,
        question: str = "",
        semantic_contract: SemanticContract | None = None,
    ) -> LLMSqlResult:
        if not self.enabled:
            return LLMSqlResult(error="llm_disabled")
        if not cot_steps:
            return LLMSqlResult(error="empty_cot_steps")
        if not schema_graph:
            return LLMSqlResult(error="schema_graph_missing")

        messages = self._build_messages(
            cot_steps,
            schema_graph,
            question=question or schema_graph.query,
            semantic_contract=semantic_contract,
        )

        try:
            payload = self.client.chat_json(
                model=self.model,
                messages=messages,
                temperature=0,
                timeout_seconds=self.timeout_seconds,
            )
        except Exception as exc:
            return LLMSqlResult(error=str(exc))

        return self._parse_result(payload)

    def _build_messages(
        self,
        cot_steps: list[QueryPlanCoT],
        schema_graph: SchemaGraph,
        *,
        question: str = "",
        semantic_contract: SemanticContract | None = None,
    ) -> list[dict[str, str]]:
        cot_text = json.dumps(
            [
                {
                    "step": s.step,
                    "processing_objects": s.processing_objects,
                    "operation_instructions": s.operation_instructions,
                    "output_target": s.output_target,
                }
                for s in cot_steps
            ],
            ensure_ascii=False,
            indent=2,
        )
        hard_constraints = self._hard_constraints_text(
            question=question or schema_graph.query,
            cot_steps=cot_steps,
            semantic_contract=semantic_contract,
        )

        user_prompt = f"""请生成 MaxCompute SQL。

输出 JSON 格式：
{{
  "sql": "SELECT ... FROM ... WHERE ...",
  "used_tables": ["soyoung_dw.table_name"],
  "used_fields": ["table_name.field_name"],
  "explanation": "SQL 生成说明（50字以内）"
}}

# QueryPlanCoT
{cot_text}

# 补全后的用户问题
{question or schema_graph.query}

# 必须落实的硬约束
{hard_constraints}

# SchemaGraph
{schema_graph.schema_graph_text}
"""

        return [
            {"role": "system", "content": SQL_GENERATION_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

    def _hard_constraints_text(
        self,
        *,
        question: str,
        cot_steps: list[QueryPlanCoT],
        semantic_contract: SemanticContract | None,
    ) -> str:
        constraints: list[str] = []
        if question:
            constraints.append(f"- resolved_question: {question}")
        if semantic_contract:
            if semantic_contract.time_range:
                constraints.append(f"- time_range: {semantic_contract.time_range}")
            if semantic_contract.metrics:
                constraints.append(f"- metrics: {semantic_contract.metrics}")
            if semantic_contract.dimensions:
                constraints.append(f"- dimensions: {semantic_contract.dimensions}")
            if semantic_contract.filters:
                constraints.append(f"- filters: {semantic_contract.filters}")
        if cot_steps:
            semantics = cot_steps[0].query_semantics
            if semantics:
                if semantics.time_type:
                    constraints.append(f"- cot_time_type: {semantics.time_type}")
                if semantics.metrics:
                    constraints.append(f"- cot_metrics: {semantics.metrics}")
                if semantics.dimensions:
                    constraints.append(f"- cot_dimensions: {semantics.dimensions}")
                if semantics.filters:
                    constraints.append(f"- cot_filters: {semantics.filters}")
                if semantics.top_n is not None:
                    constraints.append(f"- top_n: {semantics.top_n}")
        constraints.append(
            "- 如果问题点名城市/品项/渠道/时间/TopN，SQL 必须保留对应 WHERE 条件和 LIMIT，不得改写或省略；城市和品项必须使用 REGEXP 或 LIKE 模糊匹配，不得使用等号精确匹配。"
        )
        return "\n".join(constraints)

    def _parse_result(self, payload: dict[str, Any]) -> LLMSqlResult:
        sql = str(payload.get("sql") or "").strip()
        if not sql:
            return LLMSqlResult(error="empty_sql", raw_response=payload)

        return LLMSqlResult(
            sql=sql,
            used_tables=self._as_string_list(payload.get("used_tables")),
            used_fields=self._as_string_list(payload.get("used_fields")),
            explanation=str(payload.get("explanation") or "")[:200],
            raw_response=payload,
            generated=True,
        )

    def _as_string_list(self, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item) for item in value if str(item).strip()]
        if isinstance(value, str) and value.strip():
            return [value]
        return []
