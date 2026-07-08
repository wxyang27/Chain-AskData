import unittest

from app.knowledge_indexer.retrieval_context import RetrievalContext, RetrievalHit
from app.query_planner.planner import QueryPlanner
from app.schema_graph.builder import SchemaGraphBuilder


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

        plan = QueryPlanner().plan(
            "截至昨天各门店待核销金额 TOP10",
            retrieval_context=context,
            schema_graph=schema_graph,
        )

        self.assertGreaterEqual(len(plan.query_plan_cot), 1)
        first_step = plan.query_plan_cot[0]
        self.assertEqual(first_step.step, 1)

        # new four-tuple fields
        self.assertEqual(first_step.database, "soyoung_dw")
        self.assertGreaterEqual(len(first_step.processing_objects), 2)
        self.assertIn(
            "dm_opt_qy_order_info_all_d.left_gmv",
            first_step.processing_objects,
        )
        self.assertGreaterEqual(len(first_step.operation_instructions), 2)
        self.assertIn("待核销金额", first_step.output_target)
        self.assertIn("字段证据", first_step.evidence[0])

        # backward-compat properties still work
        self.assertIn("dm_opt_qy_order_info_all_d", first_step.objects)
        self.assertIn("left_gmv", first_step.fields)
        self.assertIn("left_num > 0", first_step.filters[0])
        self.assertIn("SUM(left_gmv)", first_step.calculation)


if __name__ == "__main__":
    unittest.main()
