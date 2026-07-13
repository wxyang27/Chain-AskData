import unittest

from app.intent_router.router import IntentRouter
from app.knowledge_indexer.retrieval_context import RetrievalContext, RetrievalHit


class IntentRouterTestCase(unittest.TestCase):
    def test_routes_field_question_to_schema_explain(self):
        context = RetrievalContext(
            query="核销人数应该用哪个字段",
            fields=[
                RetrievalHit(
                    document="字段：customer_id\n业务含义：核销人数",
                    metadata={"asset_type": "field", "field_name": "customer_id"},
                    distance=0.1,
                    rerank_score=20.0,
                )
            ],
        )

        result = IntentRouter().route("核销人数应该用哪个字段", context)

        self.assertEqual(result.intent, "schema_explain")
        self.assertIn("customer_id", result.evidence)

    def test_routes_caliber_difference_question_to_caliber_explain(self):
        context = RetrievalContext(
            query="核销收入和支付GMV有什么区别",
            fields=[
                RetrievalHit(
                    document="字段：exe_income\n业务含义：核销收入",
                    metadata={"asset_type": "field", "field_name": "exe_income"},
                    distance=0.1,
                    rerank_score=20.0,
                ),
                RetrievalHit(
                    document="字段：pay_gmv\n业务含义：支付GMV",
                    metadata={"asset_type": "field", "field_name": "pay_gmv"},
                    distance=0.1,
                    rerank_score=19.0,
                ),
            ],
        )

        result = IntentRouter().route("核销收入和支付GMV有什么区别", context)

        self.assertEqual(result.intent, "caliber_explain")
        self.assertIn("exe_income", result.evidence)
        self.assertIn("pay_gmv", result.evidence)

    def test_routes_how_to_view_penetration_to_caliber_explain(self):
        context = RetrievalContext(
            query="怎么看一个品项的大单品品项渗透率",
            fields=[
                RetrievalHit(
                    document="字段：standard_name\n业务含义：品项",
                    metadata={"asset_type": "field", "field_name": "standard_name"},
                    distance=0.1,
                    rerank_score=20.0,
                )
            ],
        )

        result = IntentRouter().route("怎么看一个品项的大单品品项渗透率？", context)

        self.assertEqual(result.intent, "caliber_explain")

    def test_routes_membership_question_to_schema_explain(self):
        context = RetrievalContext(
            query="怎么知道一个用户是不是连锁的L3以上会员",
            fields=[
                RetrievalHit(
                    document="字段：membership_level\n业务含义：会员等级",
                    metadata={"asset_type": "field", "field_name": "membership_level"},
                    distance=0.1,
                    rerank_score=20.0,
                )
            ],
        )

        result = IntentRouter().route("怎么知道一个用户是不是连锁的L3以上会员", context)

        self.assertEqual(result.intent, "schema_explain")

    def test_routes_unsupported_question_to_unknown(self):
        context = RetrievalContext(query="天气对门店收入的影响")

        result = IntentRouter().route("天气对门店收入的影响", context)

        self.assertEqual(result.intent, "unknown")
        self.assertGreaterEqual(result.confidence, 0.5)

    def test_routes_metric_query_to_nl2sql(self):
        context = RetrievalContext(
            query="最近30天门店核销收入TOP10",
            metrics=[
                RetrievalHit(
                    document="指标：核销收入",
                    metadata={"asset_type": "metric", "canonical": "execution_income"},
                    distance=0.1,
                    rerank_score=20.0,
                )
            ],
            examples=[
                RetrievalHit(
                    document="样例问题：最近30天各门店核销收入 TOP10",
                    metadata={"asset_type": "demo_query", "template_id": "store_income_top10_30d"},
                    distance=0.1,
                    rerank_score=20.0,
                )
            ],
        )

        result = IntentRouter().route("最近30天门店核销收入TOP10", context)

        self.assertEqual(result.intent, "nl2sql")


if __name__ == "__main__":
    unittest.main()
