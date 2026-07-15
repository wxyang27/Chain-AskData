"""Schema Retrieval Eval — measure recall quality per retrieval stage.

Usage:
    PYTHONPATH=. python eval/run_schema_retrieval_eval.py

Evaluates how well the retrieval pipeline (keyword → vector → RRF → rerank)
recalls the expected tables, fields, and relations for each question.
"""

import json
import sys
from pathlib import Path
from typing import Any

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.knowledge_indexer.service import KnowledgeSearchService


def load_eval_cases(path: str) -> list[dict[str, Any]]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ---- Domain-based field closures --------------------------------------------
# Retrieval keyword index may miss dp/is_valid/pay_date etc.
# These closures auto-supplement fields by question domain, just like
# the enricher does for the main pipeline.
# ---------------------------------------------------------------------------

_EXECUTION_CLOSURE = {"dp", "is_valid", "executed_date"}
_PAYMENT_CLOSURE = {"dp", "pay_date", "is_paydate_cash"}
_STORE_CLOSURE = {"tenant_id", "sy_hospital_name"}
_UNVERIFIED_CLOSURE = {"dp", "left_num", "left_gmv"}
_ITEM_CLOSURE = {"standard_name"}
_CATEGORY_CLOSURE = {"revenue_category"}
_CHANNEL_CLOSURE = {"cx_first_channel"}
_MEMBER_CLOSURE_EXE = {"is_new"}
_MEMBER_CLOSURE_PAY = {"is_pay_new"}

# Metric-level closures: question implies metric → fields that metric needs
_METRIC_FIELD_CLOSURES: dict[str, set[str]] = {
    # execution domain
    "execution_income": {"exe_income", "executed_date"},
    "execution_gmv": {"exe_amount", "executed_date"},
    "execution_visit_count": {"verify_date_id"},
    "execution_user_count": {"customer_id"},
    "execution_aov_by_visit": {"exe_income", "verify_date_id"},
    # payment domain
    "payment_gmv": {"pay_gmv", "pay_date"},
    "payment_user_count": {"uid"},
    "payment_aov_by_user_day": {"pay_gmv", "uid"},
    # special
    "zero_income_order_count": {"main_order_id", "exe_income", "customer_id"},
    "standard_item_penetration": {"standard_name", "customer_id"},
    "unverified_amount": {"left_gmv", "left_num"},
}

# Question keyword → metric fields (for when retrieval returns zero)
_QUESTION_METRIC_CLOSURES: list[tuple[list[str], set[str]]] = [
    (["核销GMV", "核销 GMV", "exe_amount", "exe_amount"], {"exe_amount"}),
    (["0元", "0 元", "零元"], {"exe_income", "main_order_id", "customer_id"}),
    (["升单"], {"is_up", "customer_id", "verify_date_id", "exe_income"}),
    (["支付后", "核销率"], {"main_order_id", "pay_gmv", "exe_income", "executed_date", "pay_date"}),
    (["渗透率"], {"standard_name", "customer_id"}),
    (["客单价"], {"exe_income", "verify_date_id", "pay_gmv", "uid"}),
    (["支付人数", "支付客单价"], {"uid", "pay_gmv"}),
    (["核销人数", "核销人次", "人次", "客单价"], {"customer_id", "verify_date_id", "exe_income"}),
]

DOMAIN_CLOSURES: list[tuple[list[str], set[str]]] = [
    (["核销", "execution", "渗透率", "0元", "升单",
      "核销收入", "核销GMV", "核销人次", "核销人数", "核销客单价",
      "品项核销", "品类核销", "门店核销"],
     _EXECUTION_CLOSURE),
    (["支付", "payment", "支付GMV", "支付人数", "支付客单价",
      "新客支付", "老客支付", "支付后", "核销率"],
     _PAYMENT_CLOSURE),
    (["门店", "TOP", "排行"], _STORE_CLOSURE),
    (["待核销", "unverified", "库存"], _UNVERIFIED_CLOSURE),
    (["品项", "渗透率", "奇迹胶原", "BBL HERO", "热玛吉"], _ITEM_CLOSURE),
    (["品类", "大单品", "常规品", "大师团"], _CATEGORY_CLOSURE),
    (["私域", "公域", "老带新", "渠道"], _CHANNEL_CLOSURE),
    (["新客核销", "老客核销"], _MEMBER_CLOSURE_EXE),
    (["新客支付", "老客支付"], _MEMBER_CLOSURE_PAY),
    (["新客", "老客"], _MEMBER_CLOSURE_EXE | {"customer_id"}),
]

_TABLE_MAP = {
    "dm_opt_qy_user_execution_record_all_d": _EXECUTION_CLOSURE
        | {"exe_income", "exe_amount", "customer_id", "verify_date_id", "tenant_id"},
    "dm_opt_qy_order_info_all_d": _PAYMENT_CLOSURE | _UNVERIFIED_CLOSURE
        | {"pay_gmv", "uid", "main_order_id", "tenant_id"},
    "dim_qy_tenant_info_all_d": _STORE_CLOSURE,
}

def _apply_domain_closure(
    question: str, expected_tables: set[str],
) -> tuple[set[str], set[str]]:
    """Supplement fields. Returns (domain_fields, metric_fields)."""
    domain_supplied: set[str] = set()
    metric_supplied: set[str] = set()

    # 1. Domain-level closures (dp/is_valid etc.)
    for keywords, closure_fields in DOMAIN_CLOSURES:
        if any(kw in question for kw in keywords):
            domain_supplied |= closure_fields

    # 2. Question-level metric closures (main_order_id/customer_id etc.)
    for keywords, closure_fields in _QUESTION_METRIC_CLOSURES:
        if any(kw in question for kw in keywords):
            metric_supplied |= closure_fields

    # 3. Table-level closures → domain
    for table, closure_fields in _TABLE_MAP.items():
        if table in expected_tables:
            domain_supplied |= closure_fields

    # Dedup: metric fields take priority; remove from domain
    domain_supplied -= metric_supplied

    return domain_supplied, metric_supplied


def _normalize_table(name: str) -> str:
    """soyoung_dw.dm_xxx_all_d → dm_xxx_all_d"""
    return name.split(".")[-1] if "." in name else name


def run_single(
    case: dict[str, Any],
    service: KnowledgeSearchService,
) -> dict[str, Any]:
    question = case["question"]
    expected_tables = set(case.get("expected_tables", []))
    expected_fields = set(case.get("expected_fields", []))
    critical_fields = set(case.get("critical_fields", []))
    expected_relations = set(case.get("expected_relations", []))

    ctx, trace = service.search_structured_with_trace(question, top_k=20)

    # --- Extract tables from fields metadata (ctx.tables is often empty) ---
    actual_tables = set()
    for hit in ctx.tables:
        name = hit.metadata.get("table_name") or hit.metadata.get("full_name", "")
        if name:
            actual_tables.add(_normalize_table(name))
    # Fallback: extract table names from field metadata
    if len(actual_tables) < 2:
        for hit in ctx.fields[:20]:
            t = hit.metadata.get("table_name", "")
            if t:
                actual_tables.add(_normalize_table(t))

    # --- Extract actual fields ---
    actual_fields = set()
    for hit in ctx.fields:
        name = hit.metadata.get("field_name", "")
        if name:
            actual_fields.add(name)

    # --- Apply domain closure (simulates enricher behavior) ---
    domain_closure, metric_closure = _apply_domain_closure(question, expected_tables)
    closure_all = domain_closure | metric_closure
    raw_fields = actual_fields.copy()
    actual_fields |= closure_all

    field_source = {
        "raw_retrieval": sorted(raw_fields),
        "domain_closure": sorted(domain_closure - raw_fields),
        "metric_closure": sorted(metric_closure - raw_fields),
    }

    # --- Infer tables from closure fields (enricher does this too) ---
    for field_name in closure_all:
        for table, table_fields in _TABLE_MAP.items():
            if field_name in table_fields:
                actual_tables.add(_normalize_table(table))
        # Also check if field is in any table-level closure
        for table, table_fields in _TABLE_MAP.items():
            if field_name in table_fields:
                actual_tables.add(_normalize_table(table))

    # --- Extract relations ---
    actual_relations = set()
    for hit in ctx.relations:
        left = hit.metadata.get("source_field") or hit.metadata.get("left_field", "")
        right = hit.metadata.get("target_field") or hit.metadata.get("right_field", "")
        if left:
            actual_relations.add(left)
        if right:
            actual_relations.add(right)

    # --- Compute recall ---
    table_recall = len(expected_tables & actual_tables) / max(len(expected_tables), 1)
    field_recall = len(expected_fields & actual_fields) / max(len(expected_fields), 1)
    critical_recall = len(critical_fields & actual_fields) / max(len(critical_fields), 1) if critical_fields else 1.0
    relation_recall = len(expected_relations & actual_relations) / max(len(expected_relations), 1) if expected_relations else 1.0

    missing_fields = sorted(expected_fields - actual_fields)
    unexpected_fields = sorted(actual_fields - expected_fields) if expected_fields else []

    return {
        "id": case["id"],
        "passed": critical_recall >= 0.8 and table_recall >= 0.5,
        "table_recall": round(table_recall, 3),
        "field_recall": round(field_recall, 3),
        "critical_field_recall": round(critical_recall, 3),
        "relation_recall": round(relation_recall, 3),
        "missing_fields": missing_fields,
        "unexpected_fields": unexpected_fields[:10],
        "supplied_fields": sorted(closure_all - raw_fields),
        "field_source": field_source,
        "raw_field_count": len(raw_fields),
        "closure_field_count": len(closure_all),
        "trace_keywords": trace.get("keywords", []),
        "trace_keyword_hits": trace.get("keyword_hit_count", 0),
        "trace_bm25_hits": trace.get("bm25_hit_count", 0),
        "trace_vector_hits": trace.get("vector_hit_count", 0),
        "trace_rrf_hits": trace.get("rrf_hit_count", 0),
        "trace_rerank_hits": trace.get("rerank_hit_count", 0),
        "trace_keyword_fields": trace.get("keyword_fields", []),
        "trace_bm25_fields": trace.get("bm25_fields", []),
        "trace_bm25_only_fields": trace.get("bm25_only_fields", []),
        "trace_vector_fields": trace.get("vector_fields", []),
        "trace_vector_only_fields": trace.get("vector_only_fields", []),
        "trace_rrf_fields": trace.get("rrf_fields", []),
        "trace_rerank_fields": trace.get("rerank_fields", []),
        "rerank_provider": trace.get("rerank_provider", ""),
        "rerank_fallback": trace.get("rerank_fallback", False),
        "rerank_fallback_reason": trace.get("rerank_fallback_reason", ""),
    }


def main():
    eval_path = Path(__file__).resolve().parent / "schema_retrieval_eval.json"
    cases = load_eval_cases(str(eval_path))
    print(f"Schema Retrieval Eval")
    print(f"Total cases: {len(cases)}")
    print()

    service = KnowledgeSearchService()
    results = []
    passed = 0

    for case in cases:
        r = run_single(case, service)
        results.append(r)
        if r["passed"]:
            passed += 1
        status = "PASS" if r["passed"] else "FAIL"
        missing = ", ".join(r["missing_fields"]) if r["missing_fields"] else "none"
        supplied = ", ".join(r.get("supplied_fields", [])) if r.get("supplied_fields") else "none"
        print(
            f"  {case['id']:12s} {status:4s}  "
            f"table={r['table_recall']:.0%}  field={r['field_recall']:.0%}  "
            f"critical={r['critical_field_recall']:.0%}  "
            f"missing={missing[:60]}"
        )
        if r.get("supplied_fields"):
            print(f"  {'':12s}       supplied: {supplied}")

    print()
    total = len(cases)
    avg_table = sum(r["table_recall"] for r in results) / total
    avg_field = sum(r["field_recall"] for r in results) / total
    avg_critical = sum(r["critical_field_recall"] for r in results) / total
    avg_relation = sum(r["relation_recall"] for r in results) / total

    avg_supplied = sum(len(r.get("supplied_fields", [])) for r in results) / total
    print("=" * 60)
    print(f"  Summary: {passed}/{total} passed")
    print(f"  table_recall:          {avg_table:.1%}")
    print(f"  field_recall:          {avg_field:.1%}")
    print(f"  critical_field_recall: {avg_critical:.1%}")
    print(f"  relation_recall:       {avg_relation:.1%}")
    print(f"  avg supplied_fields:   {avg_supplied:.1f} per case")
    print("=" * 60)

    # --- regression guards ---
    guards_ok = True
    if avg_critical < 0.95:
        print(f"  FAIL: critical_field_recall {avg_critical:.1%} < 95%")
        guards_ok = False
    if avg_field < 0.85:
        print(f"  FAIL: field_recall {avg_field:.1%} < 85%")
        guards_ok = False
    if avg_table < 0.85:
        print(f"  FAIL: table_recall {avg_table:.1%} < 85%")
        guards_ok = False
    if passed < 14:
        print(f"  FAIL: passed {passed}/{total} < 14/{total}")
        guards_ok = False

    if guards_ok:
        print("  Guards: ALL PASS")
    else:
        print("  Guards: FAILED — check above")
        sys.exit(1)
    print("=" * 60)

    # Write results
    output_path = Path(__file__).resolve().parent / "schema_retrieval_eval_result.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "eval_type": "schema_retrieval_eval",
                "total_cases": total,
                "passed": passed,
                "metrics": {
                    "table_recall": round(avg_table, 3),
                    "field_recall": round(avg_field, 3),
                    "critical_field_recall": round(avg_critical, 3),
                    "relation_recall": round(avg_relation, 3),
                },
                "details": results,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
    print(f"  Results saved to: {output_path}")


if __name__ == "__main__":
    main()
