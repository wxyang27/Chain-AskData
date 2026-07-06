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

    def test_query_returns_query_plan_sql_and_validation(self):
        response = self.client.post(
            "/api/query",
            json={"question": "最近30天各门店核销收入 TOP10"},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()

        self.assertEqual(body["project"], "Chain-AskData")
        self.assertIn("最近30天各门店核销收入 TOP10", body["question_summary"])
        self.assertEqual(body["query_plan"]["intent"], "nl2sql")
        self.assertIn("store_exe_income", body["query_plan"]["metrics"][0]["canonical"])
        self.assertIn("SELECT", body["sql"])
        self.assertIn("sy_hospital_name", body["sql"])
        self.assertTrue(body["validation"]["passed"])


if __name__ == "__main__":
    unittest.main()
