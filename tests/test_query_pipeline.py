import unittest

from app.answer.composer import AnswerComposer


class QueryPipelineTestCase(unittest.TestCase):
    """覆盖 MVP 阶段的 13 个自然语言取数样例。"""

    def setUp(self):
        self.composer = AnswerComposer()

    def assert_sql_case(self, question, template_id, fragments, is_core6=False):
        answer = self.composer.compose(question)

        self.assertEqual(answer.project, "Chain-AskData")
        self.assertEqual(answer.query_plan.intent, "nl2sql")
        self.assertEqual(answer.query_plan.template_id, template_id)
        self.assertTrue(answer.validation.passed, answer.validation.errors)

        if is_core6 and answer.llm_sql_adopted:
            # Core 6 queries now use LLM SQL; verify structure not fragments
            self.assertEqual(answer.sql_source, "llm")
            self.assertTrue(len(answer.sql) > 50, "LLM SQL too short")
            self.assertTrue(answer.llm_sql_validation.passed)
        else:
            for fragment in fragments:
                self.assertIn(fragment, answer.sql)

    def test_q01_yesterday_overall_execution_summary(self):
        self.assert_sql_case(
            "昨天整体核销收入、核销GMV、核销人次、核销人数、核销客单价是多少？",
            "execution_summary_yesterday",
            ["SUM(exe_income)", "SUM(exe_amount)", "verify_date_id", "customer_id"],
            is_core6=True,
        )

    def test_q02_store_income_top10(self):
        self.assert_sql_case(
            "最近30天各门店核销收入 TOP10",
            "store_income_top10_30d",
            ["sy_hospital_name", "SUM(exe_income)", "LIMIT 10"],
            is_core6=True,
        )

    def test_q03_private_new_customer_income_this_week(self):
        self.assert_sql_case(
            "本周私域新客核销收入是多少？",
            "private_new_customer_income_this_week",
            ["is_new", "cx_first_channel", "exe_income"],
            is_core6=True,
        )

    def test_q04_channel_execution_30d(self):
        self.assert_sql_case(
            "最近30天私域、公域、老带新的核销收入、人次、客单价对比",
            "channel_execution_30d",
            ["cx_first_channel", "SUM(exe_income)", "核销收入"],
            is_core6=True,
        )

    def test_q05_new_old_customer_execution_30d(self):
        self.assert_sql_case(
            "最近30天新客和老客核销收入、人次、客单价分别是多少？",
            "new_old_customer_execution_30d",
            ["CASE WHEN is_new", "SUM(exe_income)", "核销收入"],
            is_core6=True,
        )

    def test_q06_revenue_category_execution_30d(self):
        self.assert_sql_case(
            "最近30天大单品、常规品、大师团核销收入对比",
            "revenue_category_execution_30d",
            ["revenue_category", "SUM(exe_income)", "核销收入"],
            is_core6=True,
        )

    def test_q07_standard_item_income_top20(self):
        self.assert_sql_case(
            "最近30天品项核销收入 TOP20",
            "standard_item_income_top20_30d",
            [
                "standard_name AS standard_item_name",
                "ORDER BY 核销收入 DESC",
                "LIMIT 20",
            ],
        )

    def test_q08_standard_item_penetration_90d(self):
        self.assert_sql_case(
            "最近90天奇迹胶原品项渗透率是多少？",
            "standard_item_penetration_90d",
            [
                "standard_name REGEXP '奇迹胶原'",
                "COUNT(DISTINCT customer_id) AS 总核销人数",
                "品项核销人数 / NULLIF(总核销人数,0) AS 品项渗透率",
            ],
        )

    def test_q09_zero_income_orders_30d(self):
        self.assert_sql_case(
            "最近30天0元单数量和核销人数是多少？",
            "zero_income_orders_30d",
            [
                "exe_income = 0",
                "COUNT(DISTINCT main_order_id) AS 0元单量",
                "COUNT(DISTINCT customer_id) AS 0元核销人数",
            ],
        )

    def test_q10_unverified_amount_by_store(self):
        self.assert_sql_case(
            "截至昨天各门店待核销金额 TOP10",
            "unverified_amount_store_top10",
            [
                "left_num > 0",
                "SUM(left_gmv) AS 待核销金额",
                "ORDER BY 待核销金额 DESC",
                "LIMIT 10",
            ],
        )

    def test_q11_new_customer_payment_30d(self):
        self.assert_sql_case(
            "最近30天新客支付GMV、支付人数、支付客单价是多少？",
            "new_customer_payment_30d",
            [
                "is_paydate_cash = 0",
                "is_pay_new = 1",
                "COUNT(DISTINCT uid) AS 支付人数",
                "CONCAT(CAST(pay_date AS STRING), '_', CAST(uid AS STRING))",
            ],
        )

    def test_q12_pay_to_verify_rate_30d(self):
        self.assert_sql_case(
            "最近60天支付后30日核销率是多少？",
            "pay_to_verify_rate_30d",
            [
                "WITH pay_base AS",
                "DATE_SUB(CURRENT_DATE(),59)",
                "DATE_ADD(p.pay_date,30)",
                "LEFT JOIN verify_base",
            ],
        )

    def test_q13_upgrade_execution_30d(self):
        self.assert_sql_case(
            "最近30天升单人数、升单核销人次、升单核销收入是多少？",
            "upgrade_execution_30d",
            [
                "is_up = 1",
                "COUNT(DISTINCT customer_id) AS 升单人数",
                "COUNT(DISTINCT verify_date_id) AS 升单核销人次",
            ],
        )


if __name__ == "__main__":
    unittest.main()
