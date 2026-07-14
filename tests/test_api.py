import unittest

from fastapi.testclient import TestClient

from app.main import create_app


class ApiTestCase(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(create_app())

    def test_health_returns_project_status(self):
        response = self.client.get("/api/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["project"], "Chain-AskData")
        self.assertEqual(response.json()["status"], "ok")

    def test_demo_queries_returns_mvp_cases(self):
        response = self.client.get("/api/demo-queries")

        self.assertEqual(response.status_code, 200)
        body = response.json()

        self.assertEqual(len(body), 13)
        self.assertEqual(body[0]["case_id"], "Q001")
        self.assertEqual(body[1]["template_id"], "store_income_top10_30d")

    def test_knowledge_search_returns_reranked_chunks(self):
        response = self.client.get(
            "/api/knowledge/search",
            params={"q": "核销客单价的分母是什么", "top_k": 3},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()

        self.assertEqual(body["query"], "核销客单价的分母是什么")
        self.assertEqual(body["matches"][0]["metadata"]["canonical"], "execution_aov_by_visit")
        self.assertGreater(body["matches"][0]["rerank_score"], 0)
        self.assertIn("指标：核销客单价", body["matches"][0]["document"])

    def test_query_returns_query_plan_sql_validation_and_retrieval_trace(self):
        question = "最近30天各门店核销收入 TOP10"
        response = self.client.post(
            "/api/query",
            json={"question": question},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()

        self.assertEqual(body["project"], "Chain-AskData")
        self.assertIn(question, body["question_summary"])
        self.assertEqual(body["query_plan"]["intent"], "nl2sql")
        self.assertEqual(body["query_plan"]["original_question"], question)
        self.assertEqual(body["query_plan"]["template_id"], "store_income_top10_30d")
        self.assertIn(body["query_plan"]["sql_strategy"], ("rag_enhanced_template", "llm_primary", "template_fallback"))
        self.assertGreaterEqual(len(body["query_plan"]["planning_evidence"]), 1)
        self.assertIn("execution_income", body["query_plan"]["metrics"][0]["canonical"])
        self.assertIn("SELECT", body["sql"])
        self.assertIn("sy_hospital_name", body["sql"])
        self.assertTrue(body["validation"]["passed"])
        self.assertGreaterEqual(len(body["retrieval_trace"]), 1)
        self.assertIn("asset_type", body["retrieval_trace"][0]["metadata"])
        self.assertIn("metrics", body["retrieval_context"])
        self.assertIn("examples", body["retrieval_context"])
        self.assertEqual(
            body["schema_graph"]["retriever"],
            "askdata_style_schema_retriever",
        )
        self.assertGreater(body["schema_graph"]["field_count"], 0)
        self.assertIn("llm_enabled", body["query_plan"])
        self.assertIn("llm_validation_passed", body["query_plan"])


if __name__ == "__main__":
    unittest.main()
