from app.llm.query_plan_cot_generator import LLMQueryPlanCoTGenerator
from app.llm.prompts import build_query_plan_cot_messages
from app.models.query import QueryPlanCoT
from app.query_planner.planner import QueryPlanner
from app.schema_graph.graph import SchemaGraph


class FakeLLMClient:
    def __init__(self, payload=None, error: Exception | None = None):
        self.payload = payload or {}
        self.error = error
        self.calls = []

    def chat_json(self, *, model, messages, temperature=0, timeout_seconds=30):
        self.calls.append(
            {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "timeout_seconds": timeout_seconds,
            }
        )
        if self.error:
            raise self.error
        return self.payload


def test_query_plan_cot_prompt_is_readable_chinese_and_schema_grounded():
    messages = build_query_plan_cot_messages(
        question="查询核销收入",
        schema_graph_text="Table: soyoung_dw.execution_record",
    )
    prompt_text = "\n".join(message["content"] for message in messages)

    assert "数据分析规划助手" in prompt_text
    assert "不得编造" in prompt_text
    assert "查询核销收入" in prompt_text
    assert "soyoung_dw.execution_record" in prompt_text


def test_llm_cot_generator_returns_disabled_result_without_calling_client():
    client = FakeLLMClient()
    generator = LLMQueryPlanCoTGenerator(enabled=False, client=client)

    result = generator.generate(
        question="最近30天各门店核销收入 TOP10",
        schema_graph=SchemaGraph(query="最近30天各门店核销收入 TOP10"),
        fallback_steps=[],
    )

    assert result.enabled is False
    assert result.adopted is False
    assert result.fallback_reason == "llm_disabled"
    assert client.calls == []


def test_llm_cot_generator_parses_valid_qwen_json():
    client = FakeLLMClient(
        {
            "steps": [
                {
                    "step": 1,
                    "database": "soyoung_dw",
                    "processing_objects": [
                        "dm_opt_qy_user_execution_record_all_d.exe_income"
                    ],
                    "operation_instructions": [
                        "先筛选 dp = DATE_SUB(CURRENT_DATE(),1)",
                        "然后聚合 SUM(exe_income)",
                    ],
                    "output_target": "门店、核销收入",
                    "evidence": ["LLM generated from SchemaGraph"],
                }
            ]
        }
    )
    generator = LLMQueryPlanCoTGenerator(
        enabled=True,
        model="qwen-thinking",
        client=client,
    )

    result = generator.generate(
        question="最近30天各门店核销收入 TOP10",
        schema_graph=SchemaGraph(
            query="最近30天各门店核销收入 TOP10",
            fields=[
                {
                    "table_name": "dm_opt_qy_user_execution_record_all_d",
                    "field_name": "exe_income",
                }
            ],
            schema_graph_text="Table: soyoung_dw.dm_opt_qy_user_execution_record_all_d\nField: exe_income",
        ),
        fallback_steps=[],
    )

    assert result.enabled is True
    assert result.adopted is True
    assert result.model == "qwen-thinking"
    assert result.steps[0].database == "soyoung_dw"
    assert "exe_income" in result.steps[0].processing_objects[0]
    assert client.calls[0]["model"] == "qwen-thinking"
    assert result.validation_passed is True
    assert result.validation_errors == []


def test_llm_cot_generator_rejects_objects_missing_from_schema_graph():
    fallback = [
        QueryPlanCoT(
            step=1,
            database="soyoung_dw",
            processing_objects=["execution_record.exe_income"],
            operation_instructions=["先筛选，再聚合，最后输出"],
            output_target="核销收入",
        )
    ]
    client = FakeLLMClient(
        {
            "steps": [
                {
                    "step": 1,
                    "database": "soyoung_dw",
                    "processing_objects": ["invented_table.invented_field"],
                    "operation_instructions": ["先查询虚构字段"],
                    "output_target": "虚构结果",
                }
            ]
        }
    )
    generator = LLMQueryPlanCoTGenerator(enabled=True, client=client)

    result = generator.generate(
        question="查询核销收入",
        schema_graph=SchemaGraph(
            query="查询核销收入",
            fields=[
                {
                    "table_name": "execution_record",
                    "field_name": "exe_income",
                }
            ],
            schema_graph_text="Table: soyoung_dw.execution_record\nField: exe_income",
        ),
        fallback_steps=fallback,
    )

    assert result.adopted is False
    assert result.steps == fallback
    assert result.validation_passed is False
    assert "unknown_field:invented_table.invented_field" in result.validation_errors


def test_query_planner_falls_back_to_rule_cot_when_llm_fails():
    generator = LLMQueryPlanCoTGenerator(
        enabled=True,
        client=FakeLLMClient(error=RuntimeError("local qwen unavailable")),
    )
    planner = QueryPlanner(llm_cot_generator=generator)

    plan = planner.plan(
        "最近30天各门店核销收入 TOP10",
        schema_graph=SchemaGraph(
            query="最近30天各门店核销收入 TOP10",
            fields=[
                {
                    "table_name": "dm_opt_qy_user_execution_record_all_d",
                    "field_name": "exe_income",
                    "full_name": "soyoung_dw.dm_opt_qy_user_execution_record_all_d.exe_income",
                }
            ],
        ),
    )

    assert plan.query_plan_cot
    assert plan.llm_enabled is True
    assert plan.llm_adopted is False
    assert plan.llm_validation_passed is False
    assert plan.llm_validation_errors == []
    assert plan.llm_latency_ms >= 0
    assert "local qwen unavailable" in plan.llm_fallback_reason


def test_query_planner_adopts_llm_cot_when_valid():
    generator = LLMQueryPlanCoTGenerator(
        enabled=True,
        client=FakeLLMClient(
            {
                "steps": [
                    {
                        "step": 1,
                        "database": "soyoung_dw",
                        "processing_objects": ["llm_table.llm_field"],
                        "operation_instructions": ["先按 SchemaGraph 规划"],
                        "output_target": "LLM 输出目标",
                        "evidence": ["LLM generated from SchemaGraph"],
                    }
                ]
            }
        ),
    )
    planner = QueryPlanner(llm_cot_generator=generator)

    plan = planner.plan(
        "最近30天各门店核销收入 TOP10",
        schema_graph=SchemaGraph(
            query="最近30天各门店核销收入 TOP10",
            fields=[
                {
                    "table_name": "llm_table",
                    "field_name": "llm_field",
                }
            ],
        ),
    )

    assert plan.llm_enabled is True
    assert plan.llm_adopted is True
    assert plan.llm_validation_passed is True
    assert plan.llm_validation_errors == []
    assert plan.llm_repair_count == 0
    assert plan.query_plan_cot == [
        QueryPlanCoT(
            step=1,
            database="soyoung_dw",
            processing_objects=["llm_table.llm_field"],
            operation_instructions=["先按 SchemaGraph 规划"],
            output_target="LLM 输出目标",
            evidence=["LLM generated from SchemaGraph"],
        )
    ]


# ---------------------------------------------------------------------------
# Repair loop tests
# ---------------------------------------------------------------------------


class RepairFakeLLMClient:
    """Fake LLM client that simulates repair scenarios.

    Attributes:
        responses: list of payloads (or exceptions) to return in sequence.
        calls: recorded call args.
    """

    def __init__(self, responses: list):
        self.responses = responses
        self.calls: list[dict] = []
        self._call_index = 0

    def chat_json(self, *, model, messages, temperature=0, timeout_seconds=30):
        self.calls.append(
            {
                "model": model,
                "messages": messages,
                "temperature": temperature,
            }
        )
        if self._call_index >= len(self.responses):
            raise RuntimeError("no more fake responses")
        response = self.responses[self._call_index]
        self._call_index += 1
        if isinstance(response, Exception):
            raise response
        return response


def _make_schema_graph():
    return SchemaGraph(
        query="最近30天各门店核销收入 TOP10",
        fields=[
            {
                "table_name": "dm_opt_qy_user_execution_record_all_d",
                "field_name": "exe_income",
            },
            {
                "table_name": "dm_opt_qy_user_execution_record_all_d",
                "field_name": "tenant_id",
            },
            {
                "table_name": "dim_qy_tenant_info_all_d",
                "field_name": "sy_hospital_name",
            },
            {
                "table_name": "dim_qy_tenant_info_all_d",
                "field_name": "tenant_id",
            },
        ],
        relations=[
            {
                "source_table": "dm_opt_qy_user_execution_record_all_d",
                "source_field": "tenant_id",
                "target_table": "dim_qy_tenant_info_all_d",
                "target_field": "tenant_id",
            }
        ],
        schema_graph_text="Table: execution_record\nField: exe_income\nField: sy_hospital_name",
    )


def test_repair_succeeds_on_second_attempt():
    """LLM first output fails validation, repair output passes."""
    first_response = {
        "steps": [
            {
                "step": 1,
                "database": "soyoung_dw",
                "processing_objects": ["invented.field"],
                "operation_instructions": ["先瞎编"],
                "output_target": "虚构结果",
            }
        ]
    }
    second_response = {
        "steps": [
            {
                "step": 1,
                "database": "soyoung_dw",
                "processing_objects": [
                    "dm_opt_qy_user_execution_record_all_d.exe_income",
                    "dim_qy_tenant_info_all_d.sy_hospital_name",
                    "dm_opt_qy_user_execution_record_all_d.tenant_id <-> dim_qy_tenant_info_all_d.tenant_id",
                ],
                "operation_instructions": [
                    "先筛选 dp = DATE_SUB(CURRENT_DATE(),1)",
                    "再关联 tenant_id",
                    "然后聚合 SUM(exe_income) GROUP BY sy_hospital_name",
                    "最后排序 ORDER BY SUM(exe_income) DESC LIMIT 10",
                ],
                "output_target": "门店, 核销收入",
            }
        ]
    }

    client = RepairFakeLLMClient([first_response, second_response])
    generator = LLMQueryPlanCoTGenerator(enabled=True, client=client)

    result = generator.generate(
        question="最近30天各门店核销收入 TOP10",
        schema_graph=_make_schema_graph(),
        fallback_steps=[],
    )

    assert result.enabled is True
    assert result.adopted is True
    assert result.repair_count == 1
    assert result.validation_passed is True
    assert result.validation_errors == []
    assert len(client.calls) == 2

    # Verify repair message contains error context
    repair_user_msg = client.calls[1]["messages"][-1]["content"]
    assert "unknown_field" in repair_user_msg
    assert "invented.field" in repair_user_msg


def test_repair_fails_gracefully():
    """Both attempts fail validation → fallback to rule CoT."""
    bad_response = {
        "steps": [
            {
                "step": 1,
                "database": "soyoung_dw",
                "processing_objects": ["invented.field"],
                "operation_instructions": ["先瞎编"],
                "output_target": "虚构结果",
            }
        ]
    }

    fallback = [
        QueryPlanCoT(
            step=1,
            database="soyoung_dw",
            processing_objects=["execution_record.exe_income"],
            operation_instructions=["先筛选，再聚合，最后输出"],
            output_target="核销收入",
        )
    ]

    client = RepairFakeLLMClient([bad_response, bad_response])
    generator = LLMQueryPlanCoTGenerator(enabled=True, client=client)

    result = generator.generate(
        question="最近30天各门店核销收入 TOP10",
        schema_graph=_make_schema_graph(),
        fallback_steps=fallback,
    )

    assert result.adopted is False
    assert result.steps == fallback
    assert result.repair_count == 1
    assert result.validation_passed is False
    assert "unknown_field" in result.validation_errors[0]
    assert len(client.calls) == 2


def test_repair_not_attempted_when_first_call_exception():
    """If the first LLM call errors out, no repair is attempted."""
    client = RepairFakeLLMClient([RuntimeError("qwen offline")])
    generator = LLMQueryPlanCoTGenerator(enabled=True, client=client)

    fallback = [
        QueryPlanCoT(
            step=1,
            database="soyoung_dw",
            processing_objects=["execution_record.exe_income"],
            operation_instructions=["先筛选"],
            output_target="核销收入",
        )
    ]

    result = generator.generate(
        question="最近30天各门店核销收入 TOP10",
        schema_graph=_make_schema_graph(),
        fallback_steps=fallback,
    )

    assert result.adopted is False
    assert result.repair_count == 0
    assert "qwen offline" in result.fallback_reason
    assert len(client.calls) == 1


def test_repair_exception_during_repair_call_falls_back():
    """First call passes parse but fails validation; repair call errors out."""
    bad_response = {
        "steps": [
            {
                "step": 1,
                "database": "soyoung_dw",
                "processing_objects": ["invented.field"],
                "operation_instructions": ["先瞎编"],
                "output_target": "虚构结果",
            }
        ]
    }
    fallback = [
        QueryPlanCoT(
            step=1,
            database="soyoung_dw",
            processing_objects=["execution_record.exe_income"],
            operation_instructions=["先筛选"],
            output_target="核销收入",
        )
    ]

    client = RepairFakeLLMClient([bad_response, RuntimeError("repair timeout")])
    generator = LLMQueryPlanCoTGenerator(enabled=True, client=client)

    result = generator.generate(
        question="最近30天各门店核销收入 TOP10",
        schema_graph=_make_schema_graph(),
        fallback_steps=fallback,
    )

    assert result.adopted is False
    assert result.repair_count == 1
    assert result.steps == fallback
    assert len(client.calls) == 2
