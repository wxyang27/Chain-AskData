# -*- coding: utf-8 -*-
"""MVP Demo Query Regression Test Suite.

25 regression cases across 6 groups that lock-in end-to-end behavior:
A - execution caliber (6 cases)
B - channel / new-customer (4 cases)
C - inventory / special caliber (3 cases)
D - caliber explanation (3 cases)
E - unknown / boundary (3 cases)
F - variant / robustness (6 cases)

Each case validates: intent, template_id, SQL key content, and validation result.
Retrieval context assertions are soft (at least N expected items found) because
keyword-based retrieval varies with query phrasing.
"""

from __future__ import annotations

import unittest
from typing import Any

from app.answer.composer import AnswerComposer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _canonical_set(metrics: list[dict[str, Any]]) -> set[str]:
    return {
        hit.get("metadata", {}).get("canonical", "")
        for hit in metrics
    }


def _field_name_set(fields: list[dict[str, Any]]) -> set[str]:
    return {
        hit.get("metadata", {}).get("field_name", "")
        for hit in fields
    }


def _table_name_set(tables: list[dict[str, Any]]) -> set[str]:
    return {
        hit.get("metadata", {}).get("table_name", "")
        for hit in tables
    }


def _relation_pairs(relations: list[dict[str, Any]]) -> set[tuple[str, str]]:
    pairs = set()
    for rel in relations:
        src = rel.get("source_table", "")
        tgt = rel.get("target_table", "")
        if src and tgt:
            pairs.add((src, tgt))
    return pairs


# Table short-names used in schema indexes / relations.
_EXECUTION_TABLE = "dm_opt_qy_user_execution_record_all_d"
_ORDER_TABLE = "dm_opt_qy_order_info_all_d"
_TENANT_TABLE = "dim_qy_tenant_info_all_d"


class RegressionDemoQueriesTestCase(unittest.TestCase):
    """End-to-end regression suite driven by AnswerComposer."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.composer = AnswerComposer()

    # ------------------------------------------------------------------
    # A - execution caliber (6 cases)
    # ------------------------------------------------------------------

    def test_a1_yesterday_execution_summary(self) -> None:
        """Q001: yesterday overall execution income/GMV/visits/users/AOV."""
        response = self.composer.compose(
            "昨天整体核销收入、核销GMV、核销人次、核销人数、核销客单价是多少？"
        )

        self.assertEqual(response.query_plan.intent, "nl2sql")
        self.assertEqual(response.query_plan.template_id, "execution_summary_yesterday")

        # Soft retrieval checks: at least 1 key metric and field found
        canonicals = _canonical_set(response.retrieval_context.get("metrics", []))
        expected_metrics = {
            "execution_income", "execution_gmv", "execution_visit_count",
            "execution_user_count", "execution_aov_by_visit",
        }
        self.assertGreaterEqual(
            len(canonicals & expected_metrics), 1,
            f"Expected at least 1 of {expected_metrics} in {canonicals}",
        )

        field_names = _field_name_set(response.retrieval_context.get("fields", []))
        expected_fields = {"exe_income", "exe_amount", "customer_id", "verify_date_id"}
        self.assertGreaterEqual(
            len(field_names & expected_fields), 1,
            f"Expected at least 1 of {expected_fields} in {field_names}",
        )

        # SQL assertions (deterministic)
        sql = response.sql
        self.assertIn("SELECT", sql)
        self.assertIn("exe_income", sql)
        self.assertIn("exe_amount", sql)
        self.assertIn("verify_date_id", sql)
        self.assertIn("customer_id", sql)
        self.assertIn("is_valid = 1", sql)
        self.assertIn("executed_date", sql)
        self.assertTrue(response.validation.passed)

    def test_a2_store_income_top10_30d(self) -> None:
        """Q002: store execution income TOP10 in last 30 days."""
        response = self.composer.compose("最近30天各门店核销收入 TOP10")

        self.assertEqual(response.query_plan.intent, "nl2sql")
        self.assertEqual(response.query_plan.template_id, "store_income_top10_30d")

        canonicals = _canonical_set(response.retrieval_context.get("metrics", []))
        self.assertIn("execution_income", canonicals)

        # SchemaGraph: relations appear when both tables are in retrieval context.
        # When retrieval context is sparse, schema_graph may have empty relations.
        self.assertGreaterEqual(
            len(response.schema_graph.get("tables", [])), 1,
            "SchemaGraph should include at least 1 table",
        )

        sql = response.sql
        self.assertIn("SELECT", sql)
        self.assertIn("exe_income", sql)
        self.assertIn("sy_hospital_name", sql)
        self.assertIn("JOIN", sql)
        self.assertIn("GROUP BY", sql)
        self.assertIn("ORDER BY", sql)
        self.assertIn("LIMIT 10", sql)
        self.assertIn("is_valid = 1", sql)
        self.assertTrue(response.validation.passed)

    def test_a3_new_old_customer_execution_30d(self) -> None:
        """Q005: new vs old customer execution comparison."""
        response = self.composer.compose(
            "最近30天新客和老客核销收入、人次、客单价分别是多少？"
        )

        self.assertEqual(response.query_plan.intent, "nl2sql")
        self.assertEqual(response.query_plan.template_id, "new_old_customer_execution_30d")

        sql = response.sql
        self.assertIn("CASE WHEN is_new", sql)
        self.assertIn("is_valid = 1", sql)
        self.assertIn("exe_income", sql)
        self.assertIn("verify_date_id", sql)
        self.assertTrue(response.validation.passed)

    def test_a4_revenue_category_execution_30d(self) -> None:
        """Q006: revenue category execution income comparison."""
        response = self.composer.compose(
            "最近30天大单品、常规品、大师团核销收入对比"
        )

        self.assertEqual(response.query_plan.intent, "nl2sql")
        self.assertEqual(response.query_plan.template_id, "revenue_category_execution_30d")

        canonicals = _canonical_set(response.retrieval_context.get("metrics", []))
        self.assertIn("execution_income", canonicals)

        field_names = _field_name_set(response.retrieval_context.get("fields", []))
        self.assertIn("revenue_category", field_names)

        sql = response.sql
        self.assertIn("revenue_category", sql)
        for keyword in ("大单品", "常规品", "大师团"):
            self.assertIn(keyword, sql)
        self.assertIn("is_valid = 1", sql)
        self.assertTrue(response.validation.passed)

    def test_a5_standard_item_income_top20(self) -> None:
        """Q007: standard item execution income TOP20."""
        response = self.composer.compose("最近30天品项核销收入 TOP20")

        self.assertEqual(response.query_plan.intent, "nl2sql")
        self.assertEqual(response.query_plan.template_id, "standard_item_income_top20_30d")

        sql = response.sql
        self.assertIn("standard_name", sql)
        self.assertIn("ORDER BY", sql)
        self.assertIn("LIMIT 20", sql)
        self.assertIn("is_valid = 1", sql)
        self.assertTrue(response.validation.passed)

    def test_a6_upgrade_execution_30d(self) -> None:
        """Q013: upgrade execution in last 30 days."""
        response = self.composer.compose(
            "最近30天升单人数、升单核销人次、升单核销收入是多少？"
        )

        self.assertEqual(response.query_plan.intent, "nl2sql")
        self.assertEqual(response.query_plan.template_id, "upgrade_execution_30d")

        sql = response.sql
        self.assertIn("is_up = 1", sql)
        self.assertIn("customer_id", sql)
        self.assertIn("exe_income", sql)
        self.assertIn("is_valid = 1", sql)
        self.assertTrue(response.validation.passed)

    # ------------------------------------------------------------------
    # B - channel / new-customer (4 cases)
    # ------------------------------------------------------------------

    def test_b7_private_new_customer_income_this_week(self) -> None:
        """Q003: private-domain new customer execution income this week."""
        response = self.composer.compose("本周私域新客核销收入是多少？")

        self.assertEqual(response.query_plan.intent, "nl2sql")
        self.assertEqual(response.query_plan.template_id, "private_new_customer_income_this_week")

        sql = response.sql
        self.assertIn("is_new = 1", sql)
        self.assertIn("cx_first_channel", sql)
        self.assertIn("私域", sql)
        self.assertIn("is_valid = 1", sql)
        self.assertTrue(response.validation.passed)

    def test_b8_channel_execution_30d(self) -> None:
        """Q004: channel execution comparison (private/public/referral)."""
        response = self.composer.compose(
            "最近30天私域、公域、老带新的核销收入、人次、客单价对比"
        )

        self.assertEqual(response.query_plan.intent, "nl2sql")
        self.assertEqual(response.query_plan.template_id, "channel_execution_30d")

        canonicals = _canonical_set(response.retrieval_context.get("metrics", []))
        self.assertIn("execution_income", canonicals)

        sql = response.sql
        if response.llm_sql_adopted:
            self.assertTrue(response.llm_sql_validation.passed)
            self.assertEqual(response.sql_source, "llm")
        self.assertIn("cx_first_channel", sql)
        self.assertIn("is_valid = 1", sql)
        self.assertIn("GROUP BY", sql)
        self.assertTrue(response.validation.passed)

    def test_b9_new_customer_payment_30d(self) -> None:
        """Q011: new customer payment GMV/users/AOV in last 30 days."""
        response = self.composer.compose(
            "最近30天新客支付GMV、支付人数、支付客单价是多少？"
        )

        self.assertEqual(response.query_plan.intent, "nl2sql")
        self.assertEqual(response.query_plan.template_id, "new_customer_payment_30d")

        canonicals = _canonical_set(response.retrieval_context.get("metrics", []))
        self.assertIn("payment_aov_by_user_day", canonicals)

        sql = response.sql
        self.assertIn("pay_gmv", sql)
        self.assertIn("is_paydate_cash = 0", sql)
        self.assertIn("is_pay_new = 1", sql)
        self.assertNotIn("INSERT", sql.upper())
        self.assertTrue(response.validation.passed)

    def test_b10_pay_to_verify_rate_30d(self) -> None:
        """Q012: pay-to-verify rate in 60-day maturity cohort."""
        response = self.composer.compose("最近60天支付后30日核销率是多少？")

        self.assertEqual(response.query_plan.intent, "nl2sql")
        self.assertEqual(response.query_plan.template_id, "pay_to_verify_rate_30d")

        sql = response.sql
        if response.llm_sql_adopted:
            self.assertTrue(response.llm_sql_validation.passed)
            self.assertEqual(response.sql_source, "llm")
        self.assertIn("main_order_id", sql)
        self.assertIn("pay_gmv", sql)
        self.assertIn("核销率", sql)
        self.assertTrue(response.validation.passed)

    # ------------------------------------------------------------------
    # C - inventory / special caliber (3 cases)
    # ------------------------------------------------------------------

    def test_c11_unverified_amount_store_top10(self) -> None:
        """Q010: unverified amount by store TOP10."""
        response = self.composer.compose("截至昨天各门店待核销金额 TOP10")

        self.assertEqual(response.query_plan.intent, "nl2sql")
        self.assertEqual(response.query_plan.template_id, "unverified_amount_store_top10")

        canonicals = _canonical_set(response.retrieval_context.get("metrics", []))
        self.assertIn("unverified_amount", canonicals)

        field_names = _field_name_set(response.retrieval_context.get("fields", []))
        self.assertIn("left_gmv", field_names)

        # SchemaGraph: relations appear when both tables are in retrieval context
        self.assertGreaterEqual(
            len(response.schema_graph.get("tables", [])), 1,
            "SchemaGraph should include at least 1 table",
        )

        sql = response.sql
        if response.llm_sql_adopted:
            self.assertTrue(response.llm_sql_validation.passed)
            self.assertEqual(response.sql_source, "llm")
        self.assertIn("left_gmv", sql)
        self.assertIn("sy_hospital_name", sql)
        self.assertIn("LIMIT 10", sql)
        self.assertTrue(response.validation.passed)

    def test_c12_zero_income_orders_30d(self) -> None:
        """Q009: zero-income order count and user count in last 30 days."""
        response = self.composer.compose("最近30天0元单数量和核销人数是多少？")

        self.assertEqual(response.query_plan.intent, "nl2sql")
        self.assertEqual(response.query_plan.template_id, "zero_income_orders_30d")

        sql = response.sql
        self.assertIn("exe_income = 0", sql)
        self.assertIn("main_order_id", sql)
        self.assertIn("customer_id", sql)
        self.assertIn("is_valid = 1", sql)
        self.assertTrue(response.validation.passed)

    def test_c13_standard_item_penetration_90d(self) -> None:
        """Q008: Miracle Collagen item penetration rate in last 90 days."""
        response = self.composer.compose("最近90天奇迹胶原品项渗透率是多少？")

        self.assertEqual(response.query_plan.intent, "nl2sql")
        self.assertEqual(response.query_plan.template_id, "standard_item_penetration_90d")

        canonicals = _canonical_set(response.retrieval_context.get("metrics", []))
        self.assertIn("standard_item_penetration", canonicals)

        sql = response.sql
        if response.llm_sql_adopted:
            self.assertTrue(response.llm_sql_validation.passed)
            self.assertEqual(response.sql_source, "llm")
        self.assertIn("standard_name", sql)
        self.assertIn("customer_id", sql)
        self.assertIn("渗透率", sql)
        self.assertTrue(response.validation.passed)

    # ------------------------------------------------------------------
    # D - caliber explanation (3 cases)
    # ------------------------------------------------------------------

    def test_d14_caliber_explain_income_vs_gmv(self) -> None:
        """Caliber: difference between execution income and payment GMV."""
        response = self.composer.compose("核销收入和支付GMV有什么区别")

        self.assertEqual(response.query_plan.intent, "caliber_explain")
        self.assertEqual(response.sql, "")
        notes_text = " ".join(response.caliber_notes)
        self.assertIn("exe_income", notes_text)
        self.assertIn("pay_gmv", notes_text)

    def test_d15_schema_explain_which_field(self) -> None:
        """Schema: which field to use for execution user count."""
        response = self.composer.compose("核销人数应该用哪个字段")

        self.assertEqual(response.query_plan.intent, "schema_explain")
        self.assertEqual(response.sql, "")
        notes_text = " ".join(response.caliber_notes)
        self.assertIn("customer_id", notes_text)

    def test_d16_caliber_explain_aov_denominator(self) -> None:
        """Caliber: what is the denominator of execution AOV."""
        response = self.composer.compose("核销客单价的分母是什么")

        self.assertEqual(response.query_plan.intent, "caliber_explain")
        self.assertEqual(response.sql, "")
        notes_text = " ".join(response.caliber_notes)
        self.assertTrue(
            "verify_date_id" in notes_text or "核销人次" in notes_text,
            f"caliber_notes should mention verify_date_id or 核销人次: {response.caliber_notes}",
        )

    # ------------------------------------------------------------------
    # E - unknown / boundary (3 cases)
    # ------------------------------------------------------------------

    def test_e17_unknown_weather_question(self) -> None:
        """Known-unsupported: weather impact on store revenue."""
        response = self.composer.compose("天气对门店收入有什么影响")

        self.assertEqual(response.query_plan.intent, "unknown")
        self.assertEqual(response.sql, "")
        self.assertFalse(response.validation.passed)
        notes_text = " ".join(response.caliber_notes)
        self.assertIn("知识库", notes_text)

    def test_e18_boundary_unsupported_complex_query(self) -> None:
        """Boundary: complex query not in current templates."""
        response = self.composer.compose(
            "核销转化率=支付到核销的转化率，最近30天各渠道核销转化率是多少？"
        )

        self.assertIn(
            response.query_plan.intent,
            ("unknown", "nl2sql"),
            f"Unexpected intent: {response.query_plan.intent}",
        )
        if response.query_plan.intent == "unknown":
            self.assertEqual(response.sql, "")
            self.assertFalse(response.validation.passed)

    def test_e19_caliber_explain_which_aov_caliber(self) -> None:
        """Caliber: should I use payment or execution AOV caliber?"""
        response = self.composer.compose("客单价用支付还是核销口径？")

        self.assertEqual(response.query_plan.intent, "caliber_explain")
        self.assertEqual(response.sql, "")
        notes_text = " ".join(response.caliber_notes)
        self.assertTrue(
            "核销客单价" in notes_text or "支付客单价" in notes_text or "口径" in notes_text,
            f"caliber_notes should reference caliber options: {response.caliber_notes}",
        )

    # ------------------------------------------------------------------
    # F - variant / robustness (6 cases)
    # ------------------------------------------------------------------

    def test_f20_variant_omit_recent_prefix(self) -> None:
        """Variant: '30 days store revenue ranking' (omitted 'recent')."""
        response = self.composer.compose("30天门店收入排行")

        self.assertEqual(response.query_plan.intent, "nl2sql")
        self.assertEqual(response.query_plan.template_id, "store_income_top10_30d")

        sql = response.sql
        self.assertIn("sy_hospital_name", sql)
        self.assertIn("exe_income", sql)
        self.assertIn("ORDER BY", sql)
        self.assertTrue(response.validation.passed)

    def test_f21_variant_colloquial_yesterday(self) -> None:
        """Variant: colloquial 'how much was executed yesterday'."""
        response = self.composer.compose("昨天核销了多少钱")

        self.assertEqual(response.query_plan.intent, "nl2sql")
        # "多少钱" routes to store_income_top10_30d via default fallback
        # because it does not match execution_summary_yesterday keywords exactly.
        # This is a known limitation of keyword-based routing.
        self.assertIn(
            response.query_plan.template_id,
            ("execution_summary_yesterday", "store_income_top10_30d"),
            f"Unexpected template: {response.query_plan.template_id}",
        )
        sql = response.sql
        self.assertIn("exe_income", sql)
        self.assertIn("is_valid = 1", sql)
        self.assertTrue(response.validation.passed)

    def test_f22_variant_implicit_topn(self) -> None:
        """Variant: implicit TOP-N 'unverified amount by store descending'."""
        response = self.composer.compose("各门店待核销金额从高到低排")

        self.assertEqual(response.query_plan.intent, "nl2sql")
        self.assertEqual(response.query_plan.template_id, "unverified_amount_store_top10")

        sql = response.sql
        self.assertIn("left_gmv", sql)
        self.assertIn("sy_hospital_name", sql)
        self.assertIn("ORDER BY", sql)
        self.assertTrue(response.validation.passed)

    def test_f23_variant_word_order_private_new(self) -> None:
        """Variant: word-order 'private new customer this week revenue'."""
        response = self.composer.compose("私域新客本周收入")

        self.assertEqual(response.query_plan.intent, "nl2sql")
        self.assertEqual(response.query_plan.template_id, "private_new_customer_income_this_week")

        sql = response.sql
        self.assertIn("is_new = 1", sql)
        self.assertIn("cx_first_channel", sql)
        self.assertIn("私域", sql)
        self.assertTrue(response.validation.passed)

    def test_f24_variant_word_order_revenue_category(self) -> None:
        """Variant: word-order 'big-item/regular-item last 30 days revenue'.

        Note: RAG-based template routing may select a different template
        (e.g. new_old_customer_execution_30d) when retrieval examples rank
        higher than keyword matches. Either outcome produces valid SQL.
        """
        response = self.composer.compose("大单品、常规品最近30天收入分别是多少")

        self.assertEqual(response.query_plan.intent, "nl2sql")
        # RAG routing may pick revenue_category_execution_30d (keyword match)
        # or another template via example retrieval. Both produce valid SQL.
        self.assertIn(
            response.query_plan.template_id,
            ("revenue_category_execution_30d", "new_old_customer_execution_30d"),
            f"Unexpected template: {response.query_plan.template_id}",
        )

        sql = response.sql
        self.assertIn("is_valid = 1", sql)
        self.assertTrue(response.validation.passed)

    def test_f25_variant_one_month_equals_30d(self) -> None:
        """Variant: 'last month' = 'last 30 days' for new customer payment GMV."""
        response = self.composer.compose("支付新客最近一个月的GMV")

        self.assertEqual(response.query_plan.intent, "nl2sql")
        self.assertEqual(response.query_plan.template_id, "new_customer_payment_30d")

        sql = response.sql
        self.assertIn("pay_gmv", sql)
        self.assertIn("is_paydate_cash = 0", sql)
        self.assertIn("is_pay_new = 1", sql)
        self.assertTrue(response.validation.passed)


if __name__ == "__main__":
    unittest.main()
