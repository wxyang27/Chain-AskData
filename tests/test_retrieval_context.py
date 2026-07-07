import unittest

from app.knowledge_indexer.retrieval_context import RetrievalContextBuilder


class RetrievalContextTestCase(unittest.TestCase):
    """结构化检索上下文测试。"""

    def setUp(self):
        self.builder = RetrievalContextBuilder()

    def test_groups_metric_table_relation_example_matches(self):
        matches = [
            {
                "document": "指标：核销客单价",
                "metadata": {
                    "asset_type": "metric",
                    "canonical": "execution_aov_by_visit",
                    "display_name": "核销客单价",
                },
                "distance": 0.1,
                "rerank_score": 21.5,
            },
            {
                "document": "表：soyoung_dw.dm_opt_qy_user_execution_record_all_d",
                "metadata": {
                    "asset_type": "table",
                    "table_name": "dm_opt_qy_user_execution_record_all_d",
                    "full_name": "soyoung_dw.dm_opt_qy_user_execution_record_all_d",
                },
                "distance": 0.2,
                "rerank_score": 10.0,
            },
            {
                "document": "表关系：核销事实关联门店维度",
                "metadata": {
                    "asset_type": "relation",
                    "left_table": "soyoung_dw.dm_opt_qy_user_execution_record_all_d",
                    "right_table": "soyoung_dw.dim_qy_tenant_info_all_d",
                },
                "distance": 0.3,
                "rerank_score": 8.0,
            },
            {
                "document": "样例问题：最近30天各门店核销收入 TOP10",
                "metadata": {
                    "asset_type": "demo_query",
                    "case_id": "Q002",
                    "template_id": "store_income_top10_30d",
                },
                "distance": 0.4,
                "rerank_score": 7.0,
            },
        ]

        context = self.builder.build("核销客单价", matches)

        self.assertEqual(context.metrics[0].metadata["canonical"], "execution_aov_by_visit")
        self.assertEqual(context.tables[0].metadata["table_name"], "dm_opt_qy_user_execution_record_all_d")
        self.assertEqual(context.relations[0].metadata["right_table"], "soyoung_dw.dim_qy_tenant_info_all_d")
        self.assertEqual(context.examples[0].metadata["case_id"], "Q002")
        self.assertEqual(context.top_metric_ids(), ["execution_aov_by_visit"])
        self.assertEqual(context.top_table_names(), ["dm_opt_qy_user_execution_record_all_d"])
        self.assertEqual(context.top_example_ids(), ["Q002"])

    def test_flags_ambiguous_aov_question(self):
        matches = []

        context = self.builder.build("客单价是多少", matches)

        self.assertIn("客单价存在核销口径与支付口径，请确认业务场景", context.risks)


if __name__ == "__main__":
    unittest.main()
