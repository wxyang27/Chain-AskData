"""Schema asset quality report.

Scans generated indexes and reports completeness metrics so you know
what's missing before feeding data into the online pipeline.

Usage:
    PYTHONPATH=. python -m app.schema_indexing.asset_report
"""

import json
from pathlib import Path


INDEXES_DIR = Path("knowledge/generated/indexes")
HIGH_RISK_FIELDS = {
    "exe_income", "exe_amount", "customer_id", "verify_date_id",
    "pay_gmv", "uid", "is_paydate_cash", "is_pay_new", "is_new",
    "left_gmv", "left_num", "main_order_id", "standard_name",
    "revenue_category", "cx_first_channel", "tenant_id",
    "sy_hospital_name", "city_name", "executed_date", "pay_date",
    "dp", "is_valid",
}


def _load_json(name: str) -> list:
    path = INDEXES_DIR / name
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return []


def report() -> dict:
    fields = _load_json("schema_field_keyword_index.json")
    details = _load_json("schema_field_detail_index.json")
    tables = _load_json("schema_table_index.json")
    metrics = _load_json("metric_keyword_index.json")

    print("=" * 60)
    print("  Schema Asset Quality Report")
    print("=" * 60)

    # Fields
    detail_by_id = {d["field_id"]: d for d in details}
    missing_biz = 0
    missing_desc = 0
    missing_caliber = 0
    high_risk_covered = set()

    for f in fields:
        fid = f["field_id"]
        detail = detail_by_id.get(fid, {})
        if not detail.get("business_name"):
            missing_biz += 1
        if not detail.get("field_description"):
            missing_desc += 1
        if not detail.get("caliber"):
            missing_caliber += 1
        if f.get("field_name") in HIGH_RISK_FIELDS:
            high_risk_covered.add(f["field_name"])

    print(f"\n  Fields:")
    print(f"    total:                {len(fields)}")
    print(f"    missing business_name:{missing_biz}")
    print(f"    missing description:  {missing_desc}")
    print(f"    missing caliber:      {missing_caliber}")
    print(f"    high-risk covered:    {len(high_risk_covered)}/{len(HIGH_RISK_FIELDS)}")

    # Tables
    tables_with_summary = sum(1 for t in tables if t.get("table_summary"))
    print(f"\n  Tables:")
    print(f"    total:                {len(tables)}")
    print(f"    with table_summary:   {tables_with_summary}")

    # Metrics
    print(f"\n  Metrics:")
    print(f"    total:                {len(metrics)}")

    # Keyword coverage
    kw_empty = sum(1 for f in fields if not f.get("keyword_text"))
    rerank_empty = sum(1 for f in _load_json("schema_field_rerank_index.json")
                      if not f.get("rerank_text"))
    print(f"\n  Index quality:")
    print(f"    fields missing keyword_text: {kw_empty}")
    print(f"    fields missing rerank_text:  {rerank_empty}")

    total_issues = missing_biz + missing_desc + missing_caliber + kw_empty + rerank_empty
    print(f"\n  Total issues: {total_issues}")
    print("=" * 60)

    return {
        "fields_total": len(fields),
        "missing_business_name": missing_biz,
        "missing_description": missing_desc,
        "missing_caliber": missing_caliber,
        "high_risk_covered": len(high_risk_covered),
        "tables_total": len(tables),
        "metrics_total": len(metrics),
        "keyword_missing": kw_empty,
        "rerank_missing": rerank_empty,
    }


if __name__ == "__main__":
    report()
