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
from app.schema_retrieval.objects import RecallHit, SchemaRetrievalTrace


def load_eval_cases(path: str) -> list[dict[str, Any]]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def run_single(
    case: dict[str, Any],
    service: KnowledgeSearchService,
) -> dict[str, Any]:
    question = case["question"]
    expected_tables = set(case.get("expected_tables", []))
    expected_fields = set(case.get("expected_fields", []))
    critical_fields = set(case.get("critical_fields", []))
    expected_relations = set(case.get("expected_relations", []))

    ctx = service.search_structured(question, top_k=20)

    # Use hybrid retriever trace if available
    trace: SchemaRetrievalTrace | None = None
    if hasattr(service.hybrid_retriever, "retrieve_with_trace"):
        _, trace = service.hybrid_retriever.retrieve_with_trace(
            query_text=question,
            vector_matches=ctx.raw_matches,
            top_k=10,
        )

    # Extract actual results from RetrievalContext
    actual_tables = set()
    for hit in ctx.tables:
        name = hit.metadata.get("table_name") or hit.metadata.get("full_name", "")
        if name:
            actual_tables.add(name.split(".")[-1])

    actual_fields = set()
    for hit in ctx.fields:
        name = hit.metadata.get("field_name", "")
        if name:
            actual_fields.add(name)

    actual_relations = set()
    for hit in ctx.relations:
        left = hit.metadata.get("source_field") or hit.metadata.get("left_field", "")
        right = hit.metadata.get("target_field") or hit.metadata.get("right_field", "")
        if left:
            actual_relations.add(left)
        if right:
            actual_relations.add(right)

    # Compute recall
    table_recall = len(expected_tables & actual_tables) / max(len(expected_tables), 1)
    field_recall = len(expected_fields & actual_fields) / max(len(expected_fields), 1)
    critical_recall = len(critical_fields & actual_fields) / max(len(critical_fields), 1) if critical_fields else 1.0
    relation_recall = len(expected_relations & actual_relations) / max(len(expected_relations), 1) if expected_relations else 1.0

    missing_fields = sorted(expected_fields - actual_fields)
    unexpected_fields = sorted(actual_fields - expected_fields) if expected_fields else []

    return {
        "id": case["id"],
        "passed": critical_recall >= 1.0 and table_recall >= 0.8,
        "table_recall": round(table_recall, 3),
        "field_recall": round(field_recall, 3),
        "critical_field_recall": round(critical_recall, 3),
        "relation_recall": round(relation_recall, 3),
        "missing_fields": missing_fields,
        "unexpected_fields": unexpected_fields[:10],
        "trace_keywords": trace.keywords if trace else [],
        "trace_keyword_hits": len(trace.keyword_hits) if trace else 0,
        "trace_vector_hits": len(trace.vector_hits) if trace else 0,
        "trace_rrf_hits": len(trace.rrf_hits) if trace else 0,
        "trace_rerank_hits": len(trace.rerank_hits) if trace else 0,
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
        print(
            f"  {case['id']:12s} {status:4s}  "
            f"table={r['table_recall']:.0%}  field={r['field_recall']:.0%}  "
            f"critical={r['critical_field_recall']:.0%}  "
            f"missing={missing}"
        )

    print()
    total = len(cases)
    avg_table = sum(r["table_recall"] for r in results) / total
    avg_field = sum(r["field_recall"] for r in results) / total
    avg_critical = sum(r["critical_field_recall"] for r in results) / total
    avg_relation = sum(r["relation_recall"] for r in results) / total

    print("=" * 60)
    print(f"  Summary: {passed}/{total} passed")
    print(f"  table_recall:          {avg_table:.1%}")
    print(f"  field_recall:          {avg_field:.1%}")
    print(f"  critical_field_recall: {avg_critical:.1%}")
    print(f"  relation_recall:       {avg_relation:.1%}")
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
