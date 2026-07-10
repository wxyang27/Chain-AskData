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
"""


def build_query_plan_cot_messages(
    *,
    question: str,
    schema_graph_text: str,
) -> list[dict[str, str]]:
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

# SchemaGraph
{schema_graph_text}
"""
    return [
        {"role": "system", "content": QUERY_PLAN_COT_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
