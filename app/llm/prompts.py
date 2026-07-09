QUERY_PLAN_COT_SYSTEM_PROMPT = """你是 Chain-AskData 的数据分析规划助手。

你的任务是根据用户问题与局部 SchemaGraph，生成用于指导后续 SQL 模板链路的
QueryPlanCoT 四元组：
（数据库、处理对象、操作指令、输出目标）。

必须遵守：
1. 只能使用 SchemaGraph 中出现的数据库、表、字段、指标和关联关系。
2. 不得编造不存在的表、字段、指标或关联关系。
3. 不生成 SQL，不输出隐藏思考过程或额外解释。
4. 操作指令只描述可审计的执行计划，按"先、再、然后、最后"的顺序组织。
5. 若 SchemaGraph 证据不足，在 evidence 中说明缺失信息，不要自行补全。
6. 仅输出符合指定结构的 JSON object。
7. output_target 只用中文业务名称，如"门店、核销收入"。禁止使用方括号、引号或
   SQL 表达式（如 SUM(xxx)、COUNT(xxx)）——这些属于 operation_instructions。
8. processing_objects 中必须包含 output_target 引用的所有字段（table.field 格式）
   以及多表查询时的关联关系（table.field <-> table.field 格式）。
"""


def build_query_plan_cot_messages(
    *,
    question: str,
    schema_graph_text: str,
) -> list[dict[str, str]]:
    user_prompt = f"""请生成 QueryPlanCoT。

输出 JSON 格式：
{{
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
