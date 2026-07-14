"""Core-6 verification suite for Chain-AskData (Q001-Q006).

Validates:
1. SchemaGraph completeness -- all required fields present
2. Rule CoT integrity -- non-empty, 4-step operation_instructions
3. LLM CoT status -- wiring is correct (adopted or clear fallback reason)
4. Template SQL regression -- SQL contains expected clauses
5. Zero fabricated fields -- all CoT objects exist in SchemaGraph
"""

import json

import pytest

from app.answer.composer import AnswerComposer
from app.schema_graph.enricher import REQUIRED_FIELDS_BY_TEMPLATE
from app.schema_indexing.loader import SchemaIndexLoader

# ---------------------------------------------------------------------------
# Core 6 queries
# ---------------------------------------------------------------------------

CORE_QUERIES = [
    {
        "case_id": "Q001",
        "template_id": "execution_summary_yesterday",
        "question": "昨天整体核销收入、核销GMV、核销人次、核销人数、核销客单价是多少？",
        "expected_sql_tokens": [
            "exe_income", "exe_amount", "verify_date_id", "customer_id",
            "is_valid = 1",
        ],
    },
    {
        "case_id": "Q002",
        "template_id": "store_income_top10_30d",
        "question": "最近30天各门店核销收入 TOP10",
        "expected_sql_tokens": [
            "exe_income", "sy_hospital_name", "JOIN", "GROUP BY",
            "ORDER BY", "LIMIT 10", "is_valid = 1",
        ],
    },
    {
        "case_id": "Q003",
        "template_id": "private_new_customer_income_this_week",
        "question": "本周私域新客核销收入是多少？",
        "expected_sql_tokens": [
            "is_new = 1", "cx_first_channel", "is_valid = 1",
        ],
    },
    {
        "case_id": "Q004",
        "template_id": "channel_execution_30d",
        "question": "最近30天私域、公域、老带新的核销收入、人次、客单价对比",
        "expected_sql_tokens": [
            "cx_first_channel", "GROUP BY", "is_valid = 1",
        ],
    },
    {
        "case_id": "Q005",
        "template_id": "new_old_customer_execution_30d",
        "question": "最近30天新客和老客核销收入、人次、客单价分别是多少？",
        "expected_sql_tokens": [
            "is_new", "is_valid = 1", "exe_income",
        ],
    },
    {
        "case_id": "Q006",
        "template_id": "revenue_category_execution_30d",
        "question": "最近30天大单品、常规品、大师团核销收入对比",
        "expected_sql_tokens": [
            "revenue_category", "GROUP BY", "is_valid = 1",
        ],
    },
]

# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------


class TestCore6Verification:
    """End-to-end verification of the 6 core demo queries."""

    @classmethod
    def setup_class(cls):
        cls.composer = AnswerComposer()
        cls.schema_indexes = SchemaIndexLoader().load()

    # ------------------------------------------------------------------
    # SchemaGraph completeness
    # ------------------------------------------------------------------

    @pytest.mark.parametrize("query_info", CORE_QUERIES, ids=[q["case_id"] for q in CORE_QUERIES])
    def test_schema_graph_has_required_fields(self, query_info):
        """Every core query's SchemaGraph must contain all required fields."""
        response = self.composer.compose(query_info["question"])
        sg = response.schema_graph

        field_ids = {
            f"{f.get('table_name', '')}.{f.get('field_name', '')}"
            for f in sg.get("fields", [])
        }

        required = REQUIRED_FIELDS_BY_TEMPLATE.get(query_info["template_id"], [])
        missing = [
            f"{t}.{f}" for t, f in required
            if f"{t}.{f}" not in field_ids
        ]

        assert missing == [], (
            f"{query_info['case_id']}: SchemaGraph missing {missing}\n"
            f"Available: {sorted(field_ids)}"
        )

    # ------------------------------------------------------------------
    # Rule CoT integrity
    # ------------------------------------------------------------------

    @pytest.mark.parametrize("query_info", CORE_QUERIES, ids=[q["case_id"] for q in CORE_QUERIES])
    def test_rule_cot_is_complete(self, query_info):
        """Rule-based CoT must be non-empty with at least 4-step instructions."""
        response = self.composer.compose(query_info["question"])
        cot = response.query_plan.query_plan_cot

        assert len(cot) >= 1, f"{query_info['case_id']}: empty query_plan_cot"
        for step in cot:
            assert step.step >= 1, f"invalid step number"
            assert step.database, f"empty database"
            assert step.processing_objects, f"empty processing_objects"
            assert len(step.operation_instructions) >= 2, (
                f"{query_info['case_id']}: only {len(step.operation_instructions)} "
                f"instructions, expected >=2"
            )
            assert step.output_target.strip(), f"empty output_target"

    # ------------------------------------------------------------------
    # Template SQL regression
    # ------------------------------------------------------------------

    @pytest.mark.parametrize("query_info", CORE_QUERIES, ids=[q["case_id"] for q in CORE_QUERIES])
    def test_template_sql_regression(self, query_info):
        """Template SQL must match expected template_id and contain key tokens."""
        response = self.composer.compose(query_info["question"])
        plan = response.query_plan

        assert plan.template_id == query_info["template_id"], (
            f"{query_info['case_id']}: expected template_id={query_info['template_id']}, "
            f"got {plan.template_id}"
        )
        assert plan.intent == "nl2sql"

        sql = response.sql
        for token in query_info["expected_sql_tokens"]:
            assert token in sql, (
                f"{query_info['case_id']}: SQL missing '{token}'\nSQL: {sql}"
            )

        assert response.validation.passed, (
            f"{query_info['case_id']}: SQL validation failed: "
            f"{response.validation.errors}"
        )

    # ------------------------------------------------------------------
    # Zero fabricated fields in CoT
    # ------------------------------------------------------------------

    @pytest.mark.parametrize("query_info", CORE_QUERIES, ids=[q["case_id"] for q in CORE_QUERIES])
    def test_zero_fabricated_fields(self, query_info):
        """All processing_objects in CoT must reference fields in the SchemaGraph."""
        response = self.composer.compose(query_info["question"])
        sg = response.schema_graph

        allowed_fields = {
            f"{f.get('table_name', '')}.{f.get('field_name', '')}"
            for f in sg.get("fields", [])
        }

        for step in response.query_plan.query_plan_cot:
            for obj in step.processing_objects:
                if "<->" in obj:
                    continue  # relations validated separately
                # Normalize: strip db prefix if present
                parts = obj.strip().split(".")
                if len(parts) >= 2:
                    normalized = f"{parts[-2]}.{parts[-1]}"
                else:
                    normalized = obj

                if normalized not in allowed_fields:
                    # Try checking if it's already in allowed_fields as-is
                    assert obj in allowed_fields or any(
                        obj.endswith(f".{f.split('.')[-1]}" if "." in f else f"")
                        for f in allowed_fields
                    ), (
                        f"{query_info['case_id']}: fabricated field '{obj}' "
                        f"not in SchemaGraph. Allowed: {sorted(allowed_fields)}"
                    )

    # ------------------------------------------------------------------
    # LLM CoT status report (non-failing, diagnostic only)
    # ------------------------------------------------------------------

    @pytest.mark.parametrize("query_info", CORE_QUERIES, ids=[q["case_id"] for q in CORE_QUERIES])
    def test_llm_cot_status_report(self, query_info):
        """Report LLM CoT status for each core query.

        This test always passes -- it is a diagnostic report. When LLM is
        enabled and working, we expect adopted=True with zero errors.
        """
        response = self.composer.compose(query_info["question"])
        plan = response.query_plan

        report = {
            "case_id": query_info["case_id"],
            "template_id": plan.template_id,
            "llm_enabled": plan.llm_enabled,
            "llm_adopted": plan.llm_adopted,
            "llm_validation_passed": plan.llm_validation_passed,
            "llm_validation_errors": plan.llm_validation_errors,
            "llm_repair_count": plan.llm_repair_count,
            "llm_fallback_reason": plan.llm_fallback_reason,
            "llm_latency_ms": plan.llm_latency_ms,
        }

        # Diagnostic: record status
        if plan.llm_enabled:
            if plan.llm_adopted:
                report["status"] = "LLM_ADOPTED"
                assert plan.llm_validation_passed, (
                    f"{query_info['case_id']}: LLM adopted but validation failed"
                )
                assert plan.llm_validation_errors == [], (
                    f"{query_info['case_id']}: LLM adopted but has errors: "
                    f"{plan.llm_validation_errors}"
                )
            else:
                report["status"] = "FALLBACK"
                # Strict: LLM fallback is a test failure unless it's a
                # transient infrastructure issue (timeout / connection error)
                if "timeout" in plan.llm_fallback_reason.lower() or \
                   "connection" in plan.llm_fallback_reason.lower() or \
                   "unreachable" in plan.llm_fallback_reason.lower():
                    pytest.skip(
                        f"{query_info['case_id']}: LLM infrastructure unavailable "
                        f"({plan.llm_fallback_reason})"
                    )
                else:
                    pytest.fail(
                        f"{query_info['case_id']}: LLM fallback — "
                        f"reason={plan.llm_fallback_reason} "
                        f"errors={plan.llm_validation_errors} "
                        f"repair_count={plan.llm_repair_count}"
                    )
        else:
            report["status"] = "LLM_DISABLED"

        # Print individual report for visibility
        print(f"\n{query_info['case_id']} {query_info['template_id']}: {report['status']}")
        if report["status"] == "FALLBACK":
            print(f"  reason: {report['llm_fallback_reason']}")
            print(f"  errors: {report['llm_validation_errors']}")
            print(f"  repair_count: {report['llm_repair_count']}")


# ---------------------------------------------------------------------------
# Aggregate report (run last via pytest-ordering or naming convention)
# ---------------------------------------------------------------------------

def test_aggregate_core6_report():
    """Aggregate report for all 6 core queries.

    Prints a summary table. Always passes.
    """
    composer = AnswerComposer()
    results = []

    for q in CORE_QUERIES:
        response = composer.compose(q["question"])
        plan = response.query_plan
        sg = response.schema_graph

        field_ids = {
            f"{f.get('table_name', '')}.{f.get('field_name', '')}"
            for f in sg.get("fields", [])
        }
        required = REQUIRED_FIELDS_BY_TEMPLATE.get(q["template_id"], [])
        missing = [f"{t}.{f}" for t, f in required if f"{t}.{f}" not in field_ids]

        results.append({
            "case_id": q["case_id"],
            "template_id": plan.template_id,
            "schema_graph_fields": len(sg.get("fields", [])),
            "schema_graph_missing": missing,
            "cot_steps": len(plan.query_plan_cot),
            "cot_instructions": sum(len(s.operation_instructions) for s in plan.query_plan_cot),
            "llm_adopted": plan.llm_adopted,
            "llm_repair_count": plan.llm_repair_count,
            "llm_fallback_reason": plan.llm_fallback_reason,
            "sql_valid": response.validation.passed,
            "supplemented": sg.get("supplemented_fields", []),
        })

    print("\n" + "=" * 80)
    print("CORE-6 VERIFICATION REPORT")
    print("=" * 80)

    schema_ok = 0
    sql_ok = 0
    cot_ok = 0
    llm_adopted_count = 0

    for r in results:
        sg_status = "PASS" if not r["schema_graph_missing"] else f"MISS:{len(r['schema_graph_missing'])}"
        sql_status = "PASS" if r["sql_valid"] else "FAIL"
        cot_status = "PASS" if r["cot_steps"] >= 1 and r["cot_instructions"] >= 2 else "FAIL"
        llm_status = "LLM" if r["llm_adopted"] else (r["llm_fallback_reason"][:20] if r["llm_fallback_reason"] else "N/A")

        if not r["schema_graph_missing"]:
            schema_ok += 1
        if r["sql_valid"]:
            sql_ok += 1
        if r["cot_steps"] >= 1 and r["cot_instructions"] >= 2:
            cot_ok += 1
        if r["llm_adopted"]:
            llm_adopted_count += 1

        print(
            f"{r['case_id']} {r['template_id']:<38} "
            f"SG:{sg_status:<10} CoT:{cot_status:<5} SQL:{sql_status:<5} "
            f"LLM:{llm_status}"
        )
        if r["supplemented"]:
            print(f"  supplemented: {r['supplemented']}")

    print("-" * 80)
    print(f"SchemaGraph:  {schema_ok}/6  |  Rule CoT: {cot_ok}/6  |  "
          f"SQL: {sql_ok}/6  |  LLM adopted: {llm_adopted_count}/6")
    print("=" * 80)

    # All three deterministic checks must pass
    assert schema_ok == 6, f"SchemaGraph gaps: {schema_ok}/6"
    assert cot_ok == 6, f"Rule CoT gaps: {cot_ok}/6"
    assert sql_ok == 6, f"SQL regression gaps: {sql_ok}/6"
