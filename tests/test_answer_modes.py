import unittest

from app.answer.composer import AnswerComposer


class AnswerModesTestCase(unittest.TestCase):
    def setUp(self):
        self.composer = AnswerComposer()

    def test_schema_explain_does_not_force_sql_generation(self):
        response = self.composer.compose("核销人数应该用哪个字段")

        self.assertEqual(response.query_plan.intent, "schema_explain")
        self.assertEqual(response.sql, "")
        self.assertTrue(any("customer_id" in note for note in response.caliber_notes))

    def test_caliber_explain_compares_known_calibers_without_sql(self):
        response = self.composer.compose("核销收入和支付GMV有什么区别")

        self.assertEqual(response.query_plan.intent, "caliber_explain")
        self.assertEqual(response.sql, "")
        self.assertTrue(any("exe_income" in note for note in response.caliber_notes))
        self.assertTrue(any("pay_gmv" in note for note in response.caliber_notes))

    def test_unknown_question_returns_honest_no_sql_response(self):
        response = self.composer.compose("天气对门店收入有什么影响")

        self.assertEqual(response.query_plan.intent, "unknown")
        self.assertEqual(response.sql, "")
        self.assertFalse(response.validation.passed)
        self.assertTrue(any("当前知识库" in note for note in response.caliber_notes))

    def test_response_includes_schema_graph_for_supported_query(self):
        response = self.composer.compose("截至昨天各门店待核销金额 TOP10")

        self.assertIn("schema_graph_text", response.schema_graph)
        self.assertIn("left_gmv", response.schema_graph["schema_graph_text"])
        self.assertGreaterEqual(len(response.query_plan.query_plan_cot), 1)


if __name__ == "__main__":
    unittest.main()
