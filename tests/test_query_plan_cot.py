import unittest

from app.knowledge_indexer.retrieval_context import RetrievalContext, RetrievalHit
from app.llm.query_plan_cot_generator import LLMQueryPlanCoTResult
from app.models.query import CoTSemantics, QueryPlanCoT
from app.query_planner.planner import QueryPlanner
from app.schema_graph.builder import SchemaGraphBuilder


class DisabledCotGenerator:
    def generate(self, *, question, schema_graph, fallback_steps):
        return LLMQueryPlanCoTResult(
            enabled=False,
            adopted=False,
            model="test",
            steps=fallback_steps,
            fallback_reason="test_disabled",
        )


class QueryPlanCoTTestCase(unittest.TestCase):
    def test_planner_builds_query_plan_cot_from_schema_graph(self):
        context = RetrievalContext(
            query="截至昨天各门店待核销金额 TOP10",
            metrics=[
                RetrievalHit(
                    document="指标：待核销金额",
                    metadata={"asset_type": "metric", "canonical": "unverified_amount"},
                    distance=0.1,
                    rerank_score=20.0,
                )
            ],
            fields=[
                RetrievalHit(
                    document="字段：left_gmv",
                    metadata={
                        "asset_type": "field",
                        "field_name": "left_gmv",
                        "business_name": "待核销金额",
                        "table_name": "dm_opt_qy_order_info_all_d",
                        "full_name": "soyoung_dw.dm_opt_qy_order_info_all_d.left_gmv",
                    },
                    distance=0.1,
                    rerank_score=20.0,
                ),
                RetrievalHit(
                    document="字段：left_num",
                    metadata={
                        "asset_type": "field",
                        "field_name": "left_num",
                        "business_name": "待核销服务点",
                        "table_name": "dm_opt_qy_order_info_all_d",
                        "full_name": "soyoung_dw.dm_opt_qy_order_info_all_d.left_num",
                    },
                    distance=0.1,
                    rerank_score=19.0,
                ),
            ],
            examples=[
                RetrievalHit(
                    document="样例问题：截至昨天各门店待核销金额 TOP10",
                    metadata={"asset_type": "demo_query", "template_id": "unverified_amount_store_top10"},
                    distance=0.1,
                    rerank_score=18.0,
                )
            ],
        )
        schema_graph = SchemaGraphBuilder().build(context)

        plan = QueryPlanner(llm_cot_generator=DisabledCotGenerator()).plan(
            "截至昨天各门店待核销金额 TOP10",
            retrieval_context=context,
            schema_graph=schema_graph,
        )

        self.assertGreaterEqual(len(plan.query_plan_cot), 1)
        first_step = plan.query_plan_cot[0]
        self.assertEqual(first_step.step, 1)

        # new four-tuple fields
        self.assertEqual(first_step.database, "soyoung_dw")
        self.assertGreaterEqual(len(first_step.processing_objects), 1)
        self.assertIn(
            "dm_opt_qy_order_info_all_d.left_gmv",
            first_step.processing_objects,
        )
        self.assertGreaterEqual(len(first_step.operation_instructions), 2)
        self.assertIn("待核销金额", first_step.output_target)
        self.assertGreaterEqual(len(first_step.evidence), 1)

        # backward-compat properties still work
        self.assertIn("dm_opt_qy_order_info_all_d", first_step.objects)
        self.assertIn("left_gmv", first_step.fields)
        self.assertGreaterEqual(len(first_step.operation_instructions), 1)
        self.assertIn("SUM(left_gmv)", first_step.calculation)

    def test_named_city_query_does_not_inherit_store_breakdown(self):
        planner = QueryPlanner(llm_cot_generator=object())
        step = QueryPlanCoT(
            step=1,
            database="soyoung_dw",
            processing_objects=[
                "dm_opt_qy_user_execution_record_all_d.tenant_id",
                "dim_qy_tenant_info_all_d.city_name",
            ],
            operation_instructions=[
                "先筛选 city_name = '北京市'",
                "再通过 tenant_id 关联 dim_qy_tenant_info_all_d 表",
                "最后按门店（tenant_id）聚合 SUM(exe_income)，输出门店、核销收入",
            ],
            output_target="门店、核销收入",
            query_semantics=CoTSemantics(
                metrics=["execution_income"],
                dimensions=["门店", "品项"],
                filters=["standard_name = '奇迹胶原' AND city_name = '北京市'"],
            ),
        )

        cleaned = planner._postprocess_query_plan_cot(
            "本月北京地区奇迹胶原品项的核销收入",
            [step],
        )[0]

        self.assertNotIn("门店", cleaned.query_semantics.dimensions)
        self.assertIn("品项", cleaned.query_semantics.dimensions)
        self.assertNotIn("门店", cleaned.output_target)
        self.assertFalse(
            any("按门店" in instruction for instruction in cleaned.operation_instructions)
        )

    def test_this_month_query_is_normalized_to_mtd(self):
        planner = QueryPlanner(llm_cot_generator=object())
        step = QueryPlanCoT(
            step=1,
            database="soyoung_dw",
            processing_objects=["dm_opt_qy_user_execution_record_all_d.executed_date"],
            operation_instructions=[
                "先筛选最近30天记录",
                "然后聚合 SUM(exe_income)",
            ],
            output_target="核销收入",
            query_semantics=CoTSemantics(
                metrics=["execution_income"],
                time_type="last_30d",
            ),
        )

        cleaned = planner._postprocess_query_plan_cot(
            "本月北京地区奇迹胶原品项的核销收入",
            [step],
        )[0]

        self.assertEqual(cleaned.query_semantics.time_type, "this_month_mtd")
        self.assertFalse(
            any(instruction == "先筛选最近30天记录" for instruction in cleaned.operation_instructions)
        )
        self.assertTrue(
            any("DATETRUNC(CURRENT_DATE(), 'MONTH')" in instruction for instruction in cleaned.operation_instructions)
        )

    def test_new_old_query_does_not_inherit_store_dimension(self):
        planner = QueryPlanner(llm_cot_generator=object())
        step = QueryPlanCoT(
            step=1,
            database="soyoung_dw",
            processing_objects=[
                "dm_opt_qy_user_execution_record_all_d.tenant_id",
                "dm_opt_qy_user_execution_record_all_d.is_new",
            ],
            operation_instructions=[
                "最后按门店和新老客聚合 SUM(exe_income)",
            ],
            output_target="门店、新老客、核销收入",
            query_semantics=CoTSemantics(
                metrics=["execution_income"],
                dimensions=["门店", "新老客"],
            ),
        )

        cleaned = planner._postprocess_query_plan_cot(
            "本月新老客核销收入",
            [step],
        )[0]

        self.assertNotIn("门店", cleaned.query_semantics.dimensions)
        self.assertIn("新老客", cleaned.query_semantics.dimensions)
        self.assertNotIn("门店", cleaned.output_target)

    def test_channel_comparison_adds_metrics_and_named_channel_filter_instruction(self):
        planner = QueryPlanner(llm_cot_generator=object())
        step = QueryPlanCoT(
            step=1,
            database="soyoung_dw",
            processing_objects=["dm_opt_qy_user_execution_record_all_d.cx_first_channel"],
            operation_instructions=["按 cx_first_channel 分组统计 SUM(exe_income)"],
            output_target="渠道、核销收入、人次、客单价",
            query_semantics=CoTSemantics(
                metrics=["execution_income"],
                dimensions=["渠道"],
                time_type="last_30d",
            ),
        )

        cleaned = planner._postprocess_query_plan_cot(
            "最近30天私域、公域、老带新的核销收入、人次、客单价对比",
            [step],
        )[0]

        self.assertIn("execution_visit_count", cleaned.query_semantics.metrics)
        self.assertIn("execution_aov_by_visit", cleaned.query_semantics.metrics)
        self.assertTrue(
            any("cx_first_channel IN ('私域','公域','老带新')" in instruction for instruction in cleaned.operation_instructions)
        )

    def test_named_item_adds_standard_name_filter_instruction(self):
        planner = QueryPlanner(llm_cot_generator=object())
        step = QueryPlanCoT(
            step=1,
            database="soyoung_dw",
            processing_objects=["dm_opt_qy_user_execution_record_all_d.exe_income"],
            operation_instructions=["汇总 SUM(exe_income)"],
            output_target="核销收入",
            query_semantics=CoTSemantics(metrics=["execution_income"]),
        )

        cleaned = planner._postprocess_query_plan_cot(
            "本月北京地区奇迹胶原核销收入",
            [step],
        )[0]

        self.assertTrue(
            any("standard_name" in instruction and "奇迹胶原" in instruction for instruction in cleaned.operation_instructions)
        )


if __name__ == "__main__":
    unittest.main()
