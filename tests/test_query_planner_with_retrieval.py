import unittest

from app.knowledge_indexer.retrieval_context import RetrievalContextBuilder
from app.query_planner.planner import QueryPlanner


class QueryPlannerWithRetrievalTestCase(unittest.TestCase):
    """QueryPlanner 消费 RAG 检索上下文测试。"""

    def test_uses_retrieved_example_to_select_template(self):
        context = RetrievalContextBuilder().build(
            "近一个月门店核销收入排行",
            [
                {
                    "document": "样例问题：最近30天各门店核销收入 TOP10",
                    "metadata": {
                        "asset_type": "demo_query",
                        "case_id": "Q002",
                        "template_id": "store_income_top10_30d",
                    },
                    "distance": 0.1,
                    "rerank_score": 18.0,
                },
                {
                    "document": "指标：核销收入",
                    "metadata": {
                        "asset_type": "metric",
                        "canonical": "execution_income",
                        "display_name": "核销收入",
                    },
                    "distance": 0.2,
                    "rerank_score": 12.0,
                },
            ],
        )

        plan = QueryPlanner().plan("近一个月门店核销收入排行", retrieval_context=context)

        self.assertEqual(plan.template_id, "store_income_top10_30d")
        self.assertIn("execution_income", plan.retrieved_metric_ids)
        self.assertIn("Q002", plan.retrieved_example_ids)
        self.assertTrue(any("Q002" in item for item in plan.planning_evidence))

    def test_records_metric_and_table_evidence_for_unverified_amount(self):
        context = RetrievalContextBuilder().build(
            "待核销金额 TOP10",
            [
                {
                    "document": "指标：待核销金额",
                    "metadata": {
                        "asset_type": "metric",
                        "canonical": "unverified_amount",
                        "display_name": "待核销金额",
                    },
                    "distance": 0.1,
                    "rerank_score": 16.0,
                },
                {
                    "document": "表：soyoung_dw.dm_opt_qy_order_info_all_d",
                    "metadata": {
                        "asset_type": "table",
                        "table_name": "dm_opt_qy_order_info_all_d",
                        "full_name": "soyoung_dw.dm_opt_qy_order_info_all_d",
                    },
                    "distance": 0.2,
                    "rerank_score": 15.0,
                },
            ],
        )

        plan = QueryPlanner().plan("待核销金额 TOP10", retrieval_context=context)

        self.assertIn("unverified_amount", plan.retrieved_metric_ids)
        self.assertIn("dm_opt_qy_order_info_all_d", plan.retrieved_table_names)
        self.assertIn("soyoung_dw.dm_opt_qy_order_info_all_d", plan.source_tables)
        self.assertTrue(any("unverified_amount" in item for item in plan.planning_evidence))


if __name__ == "__main__":
    unittest.main()
