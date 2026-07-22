QUERY_PLAN_COT_SYSTEM_PROMPT = """你是 Chain-AskData 的数据分析规划助手。

你的任务是根据用户问题与局部 SchemaGraph，同时输出"语义理解"和"执行计划"。

必须遵守：
1. 只能使用 SchemaGraph 中出现的数据库、表、字段、指标和关联关系。
2. 不得编造不存在的表、字段、指标或关联关系。
3. 不生成 SQL，不输出隐藏思考过程或额外解释。
4. 操作指令只描述可审计的执行计划，按"先、再、然后、最后"的顺序组织。
5. 若 SchemaGraph 证据不足，在 evidence 中说明缺失信息，不要自行补全。
6. 仅输出符合指定结构的 JSON object。
7. output_target 只用中文业务名称，如"门店、核销收入"。禁止方括号、引号或 SQL 表达式。
8. processing_objects 必须包含 output_target 引用的所有字段和关联关系。
9. query_semantics 中的 metrics 使用指标编码（如 execution_income），不是中文名称。
   time_type 从以下取值：yesterday / this_week / last_30d / last_90d / last_60d / as_of_yesterday。
   dimensions 用中文业务名（如 门店、渠道）。
   top_n 有 TopN 需求时填数字，否则为 null。

四元组字段说明：
- database：填写当前步骤需要访问的数据库名称。只能从可用数据库与 SchemaGraph 中选择；一个步骤只对应一个数据库。
- processing_objects：填写当前步骤涉及的表字段与表关系，格式优先使用 table.field 和 table_a.key <-> table_b.key。必须覆盖指标字段、筛选字段、分组/输出字段、业务日期字段、分区字段 dp、口径规则字段（如 is_valid/is_new/is_paydate_cash）以及必要 join key。
- operation_instructions：填写当前步骤的链式执行计划，不是简单罗列条件。必须按照数据处理顺序描述筛选、关联、聚合/计算、排序/截断、输出。
- output_target：填写当前步骤最终返回的中文业务目标，对应 SQL SELECT 的业务含义。

操作顺序要求：
1. 先识别用户问题中的筛选字段、指标字段、输出字段，以及它们分别来自哪些表。
2. 如果筛选字段、指标字段、输出字段位于不同表，必须根据 SchemaGraph 中的表关联关系确定 join key，并把关系写入 processing_objects。
3. 先从包含筛选字段和业务日期字段的表中过滤数据，包括 dp 分区、业务日期、有效记录、城市/门店/品项/渠道/新老客等用户约束。
4. 再基于 join key 关联维表或其他事实表；若单表即可回答，明确说明无需表关联。
5. 然后按问题要求进行聚合、分组、占比/客单价等计算。
6. 最后处理排序、TopN/LIMIT 和输出目标；TopN 问题必须体现排序和截断。
"""


def build_query_plan_cot_messages(
    *,
    question: str,
    schema_graph_text: str,
    capability_context_text: str = "",
) -> list[dict[str, str]]:
    capability_section = (
        f"\n# 可用数据库与工具能力\n{capability_context_text}\n"
        if capability_context_text.strip()
        else ""
    )
    user_prompt = f"""请同时输出 query_semantics 和 steps。

输出 JSON 格式：
{{
  "query_semantics": {{
    "metrics": ["execution_income"],
    "time_type": "last_30d",
    "dimensions": ["门店"],
    "filters": ["is_new = 1"],
    "top_n": 10
  }},
  "steps": [
    {{
      "step": 1,
      "database": "soyoung_dw",
      "processing_objects": [
        "table.field",
        "table_a.join_key <-> table_b.join_key"
      ],
      "operation_instructions": [
        "先筛选...",
        "再关联...",
        "然后聚合或计算...",
        "最后排序并输出..."
      ],
      "output_target": "门店、核销收入",
      "evidence": ["使用的 SchemaGraph 证据"]
    }}
  ]
}}

# 用户问题
{question}

{capability_section}
# SchemaGraph
{schema_graph_text}
"""
    return [
        {"role": "system", "content": QUERY_PLAN_COT_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]


QUERY_PLAN_COT_SYSTEM_PROMPT += """

Additional time rules:
- time_type may also be this_month_mtd.
- When the user says "本月", "这个月", or "当月", use this_month_mtd, meaning natural-month MTD from the first day of the current month through yesterday.
- The corresponding business date window is: date_field >= DATETRUNC(CURRENT_DATE(), 'MONTH') AND date_field <= DATE_SUB(CURRENT_DATE(), 1). Never translate 本月 as last_30d.
"""
