"""LLM-based SQL generator (shadow mode).

Generates MaxCompute SQL from a validated QueryPlanCoT + SchemaGraph.
Runs alongside template SQL but does NOT replace it yet.
"""

import json
from dataclasses import dataclass, field
from typing import Any

from app.llm.local_client import LocalLLMClient
from app.models.query import QueryPlanCoT
from app.schema_graph.graph import SchemaGraph


SQL_GENERATION_SYSTEM_PROMPT = """你是 MaxCompute SQL 生成助手。

根据已校验的 QueryPlanCoT 四元组和 SchemaGraph，生成一条可执行的 MaxCompute SQL。

必须遵守：
1. 只使用 SchemaGraph 中出现的表、字段和关联关系。
2. 不得编造不存在的表、字段或 JOIN 条件。
3. 每张日快照/全量快照表（表名以 _d 结尾，包括 _all_d）必须有且只能有 dp = DATE_SUB(CURRENT_DATE(),1)。每个表别名都必须有自己的 dp = DATE_SUB(CURRENT_DATE(),1) 条件。
   - dp 是数据版本分区，不是业务日期；业务日期范围只能写在 executed_date / pay_date 等业务日期字段上。
   - 严禁对 dp 使用 >=、<=、BETWEEN、IN 或 CURRENT_DATE()，严禁写 dp 区间。
4. 核销相关查询必须有 is_valid = 1 和 executed_date 日期范围。
5. ORDER BY 必须有 LIMIT。
6. 除法运算必须用 NULLIF(分母, 0) 防止除零错误。

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

7. 只输出 JSON，不输出解释或隐藏思考过程。
"""


SQL_GENERATION_SYSTEM_PROMPT += """

Additional business semantic rules:
- If the question names a city such as Beijing, Shanghai, Wuhan, Hangzhou, or uses a city/region condition, join dim_qy_tenant_info_all_d through tenant_id and filter dim_qy_tenant_info_all_d.city_name. Do not ignore city filters.
- city_name and area_name live on dim_qy_tenant_info_all_d for execution/order fact-table analysis unless SchemaGraph gives a more specific trusted table.
- standard_name is an item/product dimension. Never alias standard_name as store; store display should use sy_hospital_name.
- If the question names an item such as 奇迹胶原, BBL HERO, 奇迹童颜, or 热玛吉, filter by standard_name. Do not ignore named item filters.
- If the question explicitly compares 私域/公域/老带新, add cx_first_channel IN ('私域','公域','老带新') instead of grouping all channels.
- Business date windows for executed_date/pay_date must end at DATE_SUB(CURRENT_DATE(), 1). Never use executed_date <= CURRENT_DATE() or pay_date <= CURRENT_DATE().
- For 本月 / this_month_mtd, business date windows must start at DATETRUNC(CURRENT_DATE(), 'MONTH') and end at DATE_SUB(CURRENT_DATE(), 1). Never translate 本月 as the last 30 days.
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
    ) -> LLMSqlResult:
        if not self.enabled:
            return LLMSqlResult(error="llm_disabled")
        if not cot_steps:
            return LLMSqlResult(error="empty_cot_steps")
        if not schema_graph:
            return LLMSqlResult(error="schema_graph_missing")

        messages = self._build_messages(cot_steps, schema_graph)

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
    ) -> list[dict[str, str]]:
        cot_text = json.dumps(
            [
                {
                    "step": s.step,
                    "database": s.database,
                    "processing_objects": s.processing_objects,
                    "operation_instructions": s.operation_instructions,
                    "output_target": s.output_target,
                }
                for s in cot_steps
            ],
            ensure_ascii=False,
            indent=2,
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

# SchemaGraph
{schema_graph.schema_graph_text}
"""

        return [
            {"role": "system", "content": SQL_GENERATION_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

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
