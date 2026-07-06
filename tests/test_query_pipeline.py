import unittest

from app.answer.composer import AnswerComposer


class QueryPipelineTestCase(unittest.TestCase):
    def test_store_income_top10_pipeline_generates_standard_sql(self):
        composer = AnswerComposer()

        answer = composer.compose("最近30天各门店核销收入 TOP10")

        self.assertEqual(answer.project, "Chain-AskData")
        self.assertEqual(answer.query_plan.intent, "nl2sql")
        self.assertEqual(answer.query_plan.metrics[0].canonical, "store_exe_income")
        self.assertIn("b.sy_hospital_name AS 门店", answer.sql)
        self.assertIn("a.executed_date BETWEEN DATE_SUB(CURRENT_DATE(),30)", answer.sql)
        self.assertIn("ORDER BY 核销收入 DESC", answer.sql)
        self.assertIn("LIMIT 10", answer.sql)
        self.assertTrue(answer.validation.passed)


if __name__ == "__main__":
    unittest.main()
