#!/usr/bin/env python
"""Chain-AskData 黄金评测集 runner。

读取 eval/golden_eval_set.json，逐条调用 Chain-AskData /api/query，
将实际输出与结构化标准答案逐字段比对，输出 pass/fail 报告 + 错误归因。

用法:
    # 确保 Chain-AskData 服务已启动 (uvicorn app.main:app)
    python eval/run_eval.py --api http://localhost:8000 --output eval/eval_result_20260710.json

    # 只跑指定类别
    python eval/run_eval.py --api http://localhost:8000 --filter standard,synonym_rewrite

    # 只跑指定 ID
    python eval/run_eval.py --api http://localhost:8000 --ids EVAL_001,EVAL_008
"""

from __future__ import annotations

import argparse
import json
import re
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

EVAL_SET_PATH = Path(__file__).parent / "golden_eval_set.json"
DEFAULT_API = "http://localhost:8000"
DEFAULT_OUTPUT = Path(__file__).parent / f"eval_result_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
HTTP_TIMEOUT = 120  # seconds, LLM calls can be slow


# ---------------------------------------------------------------------------
# HTTP client (stdlib only, no external deps)
# ---------------------------------------------------------------------------

def call_query_api(api_base: str, question: str) -> dict:
    """POST /api/query and return the JSON response dict."""
    url = f"{api_base.rstrip('/')}/api/query"
    payload = json.dumps({"question": question}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        return {"_error": f"API 不可达: {exc}"}
    except Exception as exc:  # noqa: BLE001
        return {"_error": f"API 调用异常: {exc}"}


# ---------------------------------------------------------------------------
# Comparison helpers
# ---------------------------------------------------------------------------

def _normalize(text: str) -> str:
    """Lowercase + collapse whitespace for tolerant natural-language matching."""
    return " ".join(str(text).lower().split())


def _normalize_sql_pattern(text: str) -> str:
    """Normalize SQL snippets for tolerant pattern matching.

    This intentionally keeps the check simple and deterministic:
    - ignores case and whitespace around punctuation/operators
    - treats aliased fields like ``a.exe_income`` as ``exe_income``
    - treats ``DATE_SUB(CURRENT_DATE(), 1)`` and ``DATE_SUB(CURRENT_DATE(),1)``
      as the same expression
    """
    value = str(text).lower()
    value = re.sub(r"\s+", " ", value).strip()
    value = re.sub(r"\s*([(),=<>+\-*/])\s*", r"\1", value)
    # Strip common table aliases before fields. Avoid database-qualified
    # table names by only removing a single short alias token.
    value = re.sub(r"\b(?!soyoung_dw\b)[a-zA-Z_][\w]{0,12}\.", "", value)
    value = re.sub(r"\s+", "", value)
    return value


def _contains_any(haystack: str, needle: str) -> bool:
    """Case-insensitive SQL-aware substring check."""
    return _normalize_sql_pattern(needle) in _normalize_sql_pattern(haystack)


def _contains_all(haystack: str, needles: list[str]) -> bool:
    return all(_contains_any(haystack, n) for n in needles)


def _has_date_range(sql: str, field: str, days: int) -> bool:
    sql_n = _normalize_sql_pattern(sql)
    field_n = _normalize_sql_pattern(field)
    return (
        f"{field_n}>=date_sub(current_date(),{days})" in sql_n
        and f"{field_n}<=date_sub(current_date(),1)" in sql_n
    ) or (
        f"{field_n}betweendate_sub(current_date(),{days})anddate_sub(current_date(),1)" in sql_n
    )


def _has_yesterday_filter(sql: str, field: str) -> bool:
    sql_n = _normalize_sql_pattern(sql)
    field_n = _normalize_sql_pattern(field)
    return f"{field_n}=date_sub(current_date(),1)" in sql_n


def _has_mtd_start(sql: str, field: str) -> bool:
    sql_n = _normalize_sql_pattern(sql)
    field_n = _normalize_sql_pattern(field)
    month_start_patterns = [
        f"{field_n}>=datetrunc(current_date(),'month')",
        f"{field_n}>=date_format(current_date(),'yyyy-mm-01')",
        f"{field_n}>=concat(substr(current_date(),1,7),'-01')",
    ]
    return any(pattern in sql_n for pattern in month_start_patterns)


def _has_this_week_range(sql: str, field: str) -> bool:
    sql_n = _normalize_sql_pattern(sql)
    field_n = _normalize_sql_pattern(field)
    week_start_patterns = [
        f"{field_n}>=date_sub(current_date(),weekday(cast(current_date()asdatetime)))",
        f"{field_n}>=date_sub(current_date(),weekday(current_date()))",
        f"{field_n}>=datetrunc(current_date(),'week')",
    ]
    return any(pattern in sql_n for pattern in week_start_patterns) and (
        f"{field_n}<=date_sub(current_date(),1)" in sql_n
    )


def _has_city_beijing_filter(sql: str) -> bool:
    sql_lower = sql.lower()
    return bool(
        re.search(r"city_name\s+(?:like|=)\s*['\"]%?北京(?:市)?%?['\"]", sql_lower)
    )


def _filter_matches(sql: str, expected_filter: str) -> bool:
    """Match structured filter expectations with SQL-equivalent expressions."""
    if _contains_any(sql, expected_filter):
        return True

    semantic_filters = {
        "executed_date 近7天": lambda: _has_date_range(sql, "executed_date", 7),
        "executed_date 近30天": lambda: _has_date_range(sql, "executed_date", 30),
        "executed_date 近90天": lambda: _has_date_range(sql, "executed_date", 90),
        "pay_date 近30天": lambda: _has_date_range(sql, "pay_date", 30),
        "pay_date 近60天": lambda: _has_date_range(sql, "pay_date", 60),
        "executed_date 本周": lambda: _has_this_week_range(sql, "executed_date"),
        "pay_date 本周": lambda: _has_this_week_range(sql, "pay_date"),
        "pay_date 近14天": lambda: _has_date_range(sql, "pay_date", 14),
        "executed_date >= 本月1日": lambda: _has_mtd_start(sql, "executed_date"),
        "pay_date >= 本月1日": lambda: _has_mtd_start(sql, "pay_date"),
        "city_name LIKE '%北京%'": lambda: _has_city_beijing_filter(sql),
        "核销表: dp+is_valid+executed_date=昨天": lambda: (
            _contains_any(sql, "is_valid = 1") and _has_yesterday_filter(sql, "executed_date")
        ),
        "支付表: dp+is_paydate_cash+pay_date=昨天": lambda: (
            _contains_any(sql, "is_paydate_cash = 0") and _has_yesterday_filter(sql, "pay_date")
        ),
    }
    checker = semantic_filters.get(expected_filter)
    return bool(checker and checker())


def _check_any_of(sql: str, any_of_groups: list[list[str]]) -> bool:
    """Each group is a list of patterns; pass if ALL patterns in at least one group match."""
    if not any_of_groups:
        return True
    for group in any_of_groups:
        if _contains_all(sql, group):
            return True
    return False


# ---------------------------------------------------------------------------
# Critical rule checking (CR001-CR007)
# ---------------------------------------------------------------------------

_MTD_PATTERNS = ["datetrunc", "date_format", "yyyy-mm-01", "substr", "-01"]
_30D_FORBIDDEN = ["date_sub(current_date(),30)", "date_sub(current_date(), 30)"]


def _detect_critical_rules(case: dict, sql: str) -> list[str]:
    """Auto-detect which critical rules apply to this case."""
    question = case.get("question", "")
    expected_fields = case.get("expected_fields", [])
    expected_dims = case.get("expected_dimensions", [])
    expected_tables = case.get("expected_tables", [])
    # Start with explicit tags
    rules = list(case.get("critical_rules", []))
    sql_lower = sql.lower()

    # CR001: dp rule — applies to all nl2sql cases that use execution/payment tables
    if case.get("expected_intent") == "nl2sql" and expected_tables:
        if "CR001_dp" not in rules:
            rules.append("CR001_dp")

    # CR002: MTD rule — question contains "本月"
    if "本月" in question or "这个月" in question:
        if "CR002_mtd" not in rules:
            rules.append("CR002_mtd")

    # CR003: city rule — question mentions city, or expected dimensions/fields include city
    city_signals = ["城市", "北京", "上海", "广州", "深圳", "city_name"]
    if any(s in question or s in expected_dims or s in expected_fields for s in city_signals):
        if "CR003_city" not in rules:
            rules.append("CR003_city")

    # CR004: store rule — question mentions 门店/机构, or expected dims include store field
    store_signals = ["门店", "机构", "医院", "sy_hospital_name", "tenant_alias_name"]
    if any(s in question or s in expected_dims or s in expected_fields for s in store_signals):
        if "CR004_store" not in rules:
            rules.append("CR004_store")

    # CR005: item rule — question mentions 品项, or expected fields include standard_name
    item_signals = ["品项", "奇迹胶原", "standard_name"]
    if any(s in question or s in expected_fields for s in item_signals):
        if "CR005_item" not in rules:
            rules.append("CR005_item")

    # CR006: channel rule — question mentions 渠道/私域/公域, or expected fields include cx_first_channel
    channel_signals = ["渠道", "私域", "公域", "老带新", "cx_first_channel"]
    if any(s in question or s in expected_fields for s in channel_signals):
        if "CR006_channel" not in rules:
            rules.append("CR006_channel")

    # CR007: new/old customer rule — question mentions 新客/老客/新老客
    newold_signals = ["新客", "老客", "新老客"]
    if any(s in question for s in newold_signals):
        if "CR007_newold" not in rules:
            rules.append("CR007_newold")

    return rules


def check_critical_rule(rule_id: str, sql: str, case: dict) -> tuple[bool, str]:
    """Check a single critical rule against the SQL. Returns (passed, detail)."""
    sql_n = _normalize_sql_pattern(sql)
    sql_lower = sql.lower()

    if rule_id == "CR001_dp":
        # dp must equal DATE_SUB(CURRENT_DATE(),1), not a range
        has_dp_eq = "dp=date_sub(current_date()" in sql_n
        has_dp_range = "dpbetween" in sql_n or "dp>=" in sql_n or "dp>date_sub" in sql_n
        passed = has_dp_eq and not has_dp_range
        detail = "dp=DATE_SUB(CURRENT_DATE(),1)" if passed else (
            f"dp_eq={has_dp_eq}, dp_range={has_dp_range}"
        )
        return passed, detail

    if rule_id == "CR002_mtd":
        # Must use month-start logic, not 30-day substitute
        has_mtd = any(p in sql_n for p in _MTD_PATTERNS)
        has_30d = any(p in sql_n for p in _30D_FORBIDDEN)
        passed = has_mtd and not has_30d
        detail = "MTD logic present" if passed else (
            f"mtd_patterns={has_mtd}, 30d_forbidden={has_30d}"
        )
        return passed, detail

    if rule_id == "CR003_city":
        # Must use city_name, not bare "city"
        has_city_name = "city_name" in sql_lower
        # Check for bare city fields without flagging harmless output aliases like "AS city".
        import re as _re
        sql_without_alias = _re.sub(r"\bas\s+city\b", "", sql_lower)
        bare_city = bool(_re.search(r"(?<![._])\bcity\b(?!\s*_|_name)", sql_without_alias))
        passed = has_city_name and not bare_city
        detail = "city_name present" if passed else (
            f"city_name={has_city_name}, bare_city={bare_city}"
        )
        return passed, detail

    if rule_id == "CR004_store":
        # Must use sy_hospital_name or tenant_alias_name
        has_store = "sy_hospital_name" in sql_lower or "tenant_alias_name" in sql_lower
        has_wrong = "hospital_name" in sql_lower and "sy_hospital_name" not in sql_lower
        passed = has_store and not has_wrong
        detail = "sy_hospital_name/tenant_alias_name present" if passed else (
            f"store_field={has_store}, wrong_hospital_name={has_wrong}"
        )
        return passed, detail

    if rule_id == "CR005_item":
        # Must use standard_name, not product_name
        has_standard = "standard_name" in sql_lower
        has_product = "product_name" in sql_lower
        passed = has_standard and not has_product
        detail = "standard_name present" if passed else (
            f"standard_name={has_standard}, product_name={has_product}"
        )
        return passed, detail

    if rule_id == "CR006_channel":
        # Must use cx_first_channel, not bare channel_type
        has_cx = "cx_first_channel" in sql_lower
        has_wrong = "channel_type" in sql_lower and "cx_first_channel" not in sql_lower
        passed = has_cx and not has_wrong
        detail = "cx_first_channel present" if passed else (
            f"cx_first_channel={has_cx}, channel_type={has_wrong}"
        )
        return passed, detail

    if rule_id == "CR007_newold":
        # Execution domain → is_new; Payment domain → is_pay_new
        question = case.get("question", "")
        is_payment = "支付" in question or "pay" in sql_lower or "pay_gmv" in sql_lower
        if is_payment:
            has_correct = "is_pay_new" in sql_lower
            has_wrong = "is_new" in sql_lower and "is_pay_new" not in sql_lower
            domain = "payment"
        else:
            has_correct = "is_new" in sql_lower
            has_wrong = "is_pay_new" in sql_lower
            domain = "execution"
        passed = has_correct and not has_wrong
        detail = f"{domain}: correct={has_correct}, wrong={has_wrong}" if not passed else f"{domain}: correct field used"
        return passed, detail

    return True, "rule not applicable"


# ---------------------------------------------------------------------------
# Per-case evaluation
# ---------------------------------------------------------------------------

def evaluate_case(case: dict, response: dict) -> dict:
    """Compare a single case's expected values against the API response.

    Returns a dict with per-field pass/fail and overall verdict.
    """
    expected = case
    plan = response.get("query_plan", {})
    sql = response.get("sql", "") or ""
    llm_sql = response.get("llm_sql", "") or ""
    template_sql = response.get("template_sql", "") or ""
    sql_source = response.get("sql_source", "template")
    caliber_notes = response.get("caliber_notes", [])
    intent_actual = plan.get("intent", "")

    # The "effective SQL" to check patterns against — prefer the adopted SQL
    effective_sql = llm_sql if sql_source == "llm" and llm_sql else (sql or template_sql)
    checks: list[dict] = []

    def _add(name: str, passed: bool, detail: str = ""):
        checks.append({"check": name, "passed": passed, "detail": detail})

    # --- 1. Intent ---
    expected_intent = expected.get("expected_intent", "")
    intent_ok = intent_actual == expected_intent
    _add("intent", intent_ok, f"expected={expected_intent} actual={intent_actual}")

    # --- For non-nl2sql intents, skip SQL-structure checks but verify content ---
    if expected_intent in ("schema_explain", "caliber_explain", "unknown"):
        # Explain/unknown responses should not generate SQL.
        sql_generated = bool(effective_sql.strip())
        _add("no_sql_generated", not sql_generated,
             f"SQL should be empty for {expected_intent}, got: {effective_sql[:80]}...")

        evidence_text = _response_evidence_text(response)
        expected_terms = (
            expected.get("expected_metrics", [])
            + expected.get("expected_tables", [])
            + expected.get("expected_fields", [])
        )
        missing_evidence_terms = [
            term for term in expected_terms
            if not _contains_any(evidence_text, term)
        ]
        if expected_terms:
            _add(
                "explain_evidence",
                not missing_evidence_terms,
                (
                    f"missing={missing_evidence_terms}"
                    if missing_evidence_terms
                    else f"matched {len(expected_terms)} expected evidence terms"
                ),
            )

        if expected_intent in ("schema_explain", "caliber_explain"):
            expected_caliber = expected.get("expected_caliber", {})
            caliber_terms = _extract_key_terms(
                " ".join([
                    expected_caliber.get("definition", ""),
                    " ".join(expected_caliber.get("known_risks", []) or []),
                ])
            )
            missing_caliber_terms = [
                term for term in caliber_terms
                if not _contains_any(evidence_text, term)
            ]
            if caliber_terms:
                matched = len(caliber_terms) - len(missing_caliber_terms)
                # Explain answers are prose; require enough grounding, not exact wording.
                content_ok = matched / max(len(caliber_terms), 1) >= 0.4
                _add(
                    "explain_content",
                    content_ok,
                    f"matched {matched}/{len(caliber_terms)} key terms"
                    + (f"; missing={missing_caliber_terms}" if not content_ok else ""),
                )

        overall = all(c["passed"] for c in checks)
        return _build_result(case, response, checks, overall, sql_source, effective_sql,
                             critical_failures=[], applicable_rules=[])

    # --- 2. Metrics ---
    expected_metrics = expected.get("expected_metrics", [])
    actual_metrics_raw = plan.get("metrics", [])
    actual_metric_canonicals = {m.get("canonical", "") for m in actual_metrics_raw}
    metrics_missing = [m for m in expected_metrics if m not in actual_metric_canonicals]
    metrics_ok = len(metrics_missing) == 0
    _add("metrics", metrics_ok,
         f"missing={metrics_missing}" if metrics_missing else f"matched {len(expected_metrics)} metrics")

    # --- 3. Tables ---
    expected_tables = expected.get("expected_tables", [])
    actual_tables_raw = plan.get("source_tables", []) or []
    # Also scan SQL for table names
    sql_tables_text = effective_sql + " " + " ".join(actual_tables_raw)
    tables_missing = [t for t in expected_tables if t not in sql_tables_text]
    tables_ok = len(tables_missing) == 0
    _add("tables", tables_ok,
         f"missing={tables_missing}" if tables_missing else f"matched {len(expected_tables)} tables")

    # --- 4. Fields ---
    expected_fields = expected.get("expected_fields", [])
    retrieved_fields = plan.get("retrieved_field_names", []) or []
    llm_fields = response.get("llm_sql_detail", {}).get("used_fields", []) or []
    all_field_text = effective_sql + " " + " ".join(retrieved_fields) + " " + " ".join(llm_fields)
    fields_missing = [f for f in expected_fields if f not in all_field_text]
    fields_ok = len(fields_missing) == 0
    _add("fields", fields_ok,
         f"missing={fields_missing}" if fields_missing else f"matched {len(expected_fields)} fields")

    # --- 5. Filters (check if key filter fragments appear in SQL) ---
    expected_filters = expected.get("expected_filters", [])
    filters_missing = [f for f in expected_filters if not _filter_matches(effective_sql, f)]
    filters_ok = len(filters_missing) == 0
    _add("filters", filters_ok,
         f"missing={filters_missing}" if filters_missing else f"matched {len(expected_filters)} filters")

    # --- 6. must_contain ---
    must_contain = expected.get("expected_sql_must_contain", [])
    must_missing = [p for p in must_contain if not _contains_any(effective_sql, p)]
    must_ok = len(must_missing) == 0
    _add("must_contain", must_ok,
         f"missing={must_missing}" if must_missing else f"all {len(must_contain)} patterns present")

    # --- 7. any_of ---
    any_of = expected.get("expected_sql_any_of", [])
    any_of_ok = _check_any_of(effective_sql, any_of)
    _add("any_of", any_of_ok,
         "passed" if any_of_ok else f"none of {len(any_of)} groups matched")

    # --- 8. forbidden ---
    forbidden = expected.get("forbidden_sql_patterns", [])
    forbidden_triggered = [p for p in forbidden if _contains_any(effective_sql, p)]
    forbidden_ok = len(forbidden_triggered) == 0
    _add("forbidden", forbidden_ok,
         f"triggered={forbidden_triggered}" if forbidden_triggered else "no forbidden patterns")

    # --- 9. Caliber (heuristic: check if caliber_notes mention key terms from expected_caliber) ---
    expected_caliber = expected.get("expected_caliber", {})
    caliber_definition = expected_caliber.get("definition", "")
    caliber_risks = expected_caliber.get("known_risks", [])
    # Extract key terms from definition (field names, metric names)
    caliber_key_terms = _extract_key_terms(caliber_definition)
    caliber_text = " ".join(caliber_notes).lower()
    matched_terms = [t for t in caliber_key_terms if t.lower() in caliber_text]
    # Pass if at least 50% of key terms are mentioned, or if caliber_notes is non-empty and intent is nl2sql
    caliber_ratio = len(matched_terms) / max(len(caliber_key_terms), 1)
    caliber_ok = caliber_ratio >= 0.4 or (len(caliber_notes) > 0 and len(caliber_key_terms) <= 2)
    _add("caliber", caliber_ok,
         f"matched {len(matched_terms)}/{len(caliber_key_terms)} key terms ({caliber_ratio:.0%})")

    # --- 10. Critical rules (CR001-CR007) ---
    applicable_rules = _detect_critical_rules(case, effective_sql)
    critical_failures: list[str] = []
    for rule_id in applicable_rules:
        cr_passed, cr_detail = check_critical_rule(rule_id, effective_sql, case)
        _add(f"CR:{rule_id}", cr_passed, cr_detail)
        if not cr_passed:
            critical_failures.append(rule_id)

    # --- 11. sql_source / llm adoption checks ---
    llm_enabled = plan.get("llm_enabled", False)
    llm_adopted = response.get("llm_sql_adopted", False)
    llm_validation = response.get("llm_sql_validation", {})
    llm_val_errors = llm_validation.get("errors", []) if isinstance(llm_validation, dict) else []

    # If LLM is enabled and generated SQL, check that validation makes sense
    if llm_enabled and response.get("llm_sql_detail", {}).get("generated", False):
        # LLM SQL was generated — either adopted (passed gate) or fell back (failed gate)
        if llm_adopted:
            _add("llm_adoption", True, "LLM SQL adopted (gate passed)")
        elif llm_val_errors:
            _add("llm_adoption", True, f"LLM SQL rejected by gate, template fallback. errors={llm_val_errors[:2]}")
        else:
            _add("llm_adoption", False, "LLM SQL generated but neither adopted nor rejected — unclear state")

    # --- Overall verdict ---
    # Intent, forbidden, must_contain, critical_rules are hard gates
    hard_gates = {"intent", "forbidden", "must_contain"}
    hard_fail = any(not c["passed"] for c in checks if c["check"] in hard_gates)
    cr_fail = len(critical_failures) > 0
    soft_fail = any(not c["passed"] for c in checks if c["check"] not in hard_gates and not c["check"].startswith("CR:"))
    overall = not hard_fail and not soft_fail and not cr_fail

    return _build_result(case, response, checks, overall, sql_source, effective_sql,
                         critical_failures=critical_failures, applicable_rules=applicable_rules)


def _extract_key_terms(text: str) -> list[str]:
    """Extract field names and SQL keywords from a caliber definition string."""
    terms = []
    # Extract words that look like field names (contain _ or are SQL keywords)
    sql_keywords = {"sum", "count", "distinct", "nullif", "join", "group", "order", "limit"}
    for word in text.replace(",", " ").replace("(", " ").replace(")", " ").replace("/", " ").split():
        clean = word.strip("'\"")
        if "_" in clean and len(clean) > 2:
            terms.append(clean)
        elif clean.lower() in sql_keywords:
            terms.append(clean)
    return list(dict.fromkeys(terms))  # dedupe preserving order


def _response_evidence_text(response: dict) -> str:
    """Flatten response evidence used for explain/caliber checks."""
    parts = [
        json.dumps(response.get("query_plan", {}), ensure_ascii=False),
        json.dumps(response.get("retrieval_context", {}), ensure_ascii=False),
        json.dumps(response.get("schema_graph", {}), ensure_ascii=False),
        " ".join(response.get("caliber_notes", []) or []),
    ]
    return "\n".join(parts)


def _build_result(case: dict, response: dict, checks: list[dict],
                  overall: bool, sql_source: str, effective_sql: str,
                  critical_failures: list[str] | None = None,
                  applicable_rules: list[str] | None = None) -> dict:
    """Build the final result dict for one case."""
    failed_checks = [c for c in checks if not c["passed"]]
    # Attribution
    attribution = _attribute_failure(failed_checks, case.get("evaluation_focus", []))

    return {
        "id": case["id"],
        "question": case["question"],
        "category": case["category"],
        "difficulty": case["difficulty"],
        "expected_intent": case.get("expected_intent", ""),
        "actual_intent": response.get("query_plan", {}).get("intent", ""),
        "sql_source": sql_source,
        "llm_enabled": response.get("query_plan", {}).get("llm_enabled", False),
        "llm_adopted": response.get("llm_sql_adopted", False),
        "passed": overall,
        "checks": checks,
        "failed_checks": [c["check"] for c in failed_checks],
        "critical_failures": critical_failures or [],
        "applicable_critical_rules": applicable_rules or [],
        "attribution": attribution,
        "effective_sql": effective_sql[:500],
        "api_error": response.get("_error", ""),
        "evaluation_focus": case.get("evaluation_focus", []),
    }


def _attribute_failure(failed_checks: list[dict], focus: list[str]) -> str:
    """Map failed checks to an error source for debugging."""
    if not failed_checks:
        return "none"
    names = {c["check"] for c in failed_checks}
    if "intent" in names:
        return "IntentRouter (routing/retrieval)"
    if "metrics" in names:
        return "QueryPlanCoT (LLM planning)"
    if "tables" in names or "fields" in names:
        return "SchemaGraph (retrieval/enricher)"
    if "filters" in names or "must_contain" in names:
        return "SqlGenerator (template/LLM)"
    if "forbidden" in names:
        return "SqlSafetyGate (caliber confusion)"
    if "explain_evidence" in names:
        return "RetrievalContext/AnswerComposer (explain evidence)"
    if "explain_content" in names:
        return "AnswerComposer (explain/caliber content)"
    if "caliber" in names:
        return "AnswerComposer (caliber notes)"
    return "unknown"


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

def run_eval(api_base: str, eval_set_path: Path, output_path: Path,
             filter_categories: list[str] | None = None,
             filter_ids: list[str] | None = None) -> dict:
    """Run the full evaluation suite."""
    # Load eval set
    with open(eval_set_path, encoding="utf-8") as f:
        eval_set = json.load(f)

    meta = eval_set.get("meta", {})
    cases = eval_set.get("cases", [])

    # Apply filters
    if filter_categories:
        cases = [c for c in cases if c["category"] in filter_categories]
    if filter_ids:
        cases = [c for c in cases if c["id"] in filter_ids]

    print(f"\n{'='*70}")
    print(f"  Chain-AskData 黄金评测集 v{meta.get('version', '?')}")
    print(f"  总样例: {len(cases)} 条 | API: {api_base}")
    print(f"  通过标准: {meta.get('pass_criteria', 'N/A')}")
    print(f"{'='*70}\n")

    results = []
    pass_count = 0

    for i, case in enumerate(cases, 1):
        case_id = case["id"]
        question = case["question"]
        category = case["category"]
        difficulty = case["difficulty"]

        print(f"[{i:>2}/{len(cases)}] {case_id} [{category}/{difficulty}] {question[:40]}...", end=" ")

        # Call API
        response = call_query_api(api_base, question)

        if response.get("_error"):
            print("API ERROR")
            result = {
                "id": case_id,
                "question": question,
                "category": category,
                "difficulty": difficulty,
                "passed": False,
                "api_error": response["_error"],
                "checks": [],
                "failed_checks": ["api_error"],
                "attribution": "API unreachable",
            }
        else:
            # Evaluate
            result = evaluate_case(case, response)
            status = "PASS" if result["passed"] else "FAIL"
            failed = result.get("failed_checks", [])
            print(f"{status}" + (f" ({', '.join(failed)})" if failed else ""))

        results.append(result)
        if result["passed"]:
            pass_count += 1

    # Summary
    total = len(results)
    fail_count = total - pass_count
    pass_rate = pass_count / total * 100 if total > 0 else 0

    # Category breakdown
    by_category: dict[str, dict] = {}
    for r in results:
        cat = r["category"]
        if cat not in by_category:
            by_category[cat] = {"total": 0, "pass": 0}
        by_category[cat]["total"] += 1
        if r["passed"]:
            by_category[cat]["pass"] += 1

    # Difficulty breakdown
    by_difficulty: dict[str, dict] = {}
    for r in results:
        diff = r["difficulty"]
        if diff not in by_difficulty:
            by_difficulty[diff] = {"total": 0, "pass": 0}
        by_difficulty[diff]["total"] += 1
        if r["passed"]:
            by_difficulty[diff]["pass"] += 1

    # Attribution breakdown
    attributions: dict[str, int] = {}
    for r in results:
        if not r["passed"]:
            attr = r.get("attribution", "unknown")
            attributions[attr] = attributions.get(attr, 0) + 1

    # Critical rule stats
    cr_total = 0
    cr_pass = 0
    for r in results:
        applicable = r.get("applicable_critical_rules", [])
        failures = r.get("critical_failures", [])
        cr_total += len(applicable)
        cr_pass += len(applicable) - len(failures)
    cr_pass_rate = cr_pass / cr_total * 100 if cr_total > 0 else 0

    # Hard difficulty pass rate
    hard_total = by_difficulty.get("hard", {}).get("total", 0)
    hard_pass = by_difficulty.get("hard", {}).get("pass", 0)
    hard_pass_rate = hard_pass / hard_total * 100 if hard_total > 0 else 0

    # Quality gates
    quality_gates = meta.get("quality_gates", {})
    gate_overall = quality_gates.get("overall", 80)
    gate_hard = quality_gates.get("hard", 75)
    gate_cr = quality_gates.get("critical_rule", 95)

    gates_passed = {
        "overall_80": pass_rate >= gate_overall,
        "hard_75": hard_pass_rate >= gate_hard,
        "critical_95": cr_pass_rate >= gate_cr,
    }
    all_gates_pass = all(gates_passed.values())

    summary = {
        "total": total,
        "passed": pass_count,
        "failed": fail_count,
        "pass_rate": round(pass_rate, 1),
        "hard_pass_rate": round(hard_pass_rate, 1),
        "critical_rule_pass_rate": round(cr_pass_rate, 1),
        "critical_rule_total": cr_total,
        "critical_rule_passed": cr_pass,
        "by_category": {k: f"{v['pass']}/{v['total']}" for k, v in by_category.items()},
        "by_difficulty": {k: f"{v['pass']}/{v['total']}" for k, v in by_difficulty.items()},
        "failure_attributions": attributions,
        "quality_gates": {
            "thresholds": {"overall": gate_overall, "hard": gate_hard, "critical_rule": gate_cr},
            "actuals": {"overall": round(pass_rate, 1), "hard": round(hard_pass_rate, 1), "critical_rule": round(cr_pass_rate, 1)},
            "passed": gates_passed,
            "all_pass": all_gates_pass,
        },
    }

    report = {
        "meta": {
            "eval_set_version": meta.get("version"),
            "run_at": datetime.now().isoformat(),
            "api_base": api_base,
        },
        "summary": summary,
        "results": results,
    }

    # Save report
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    # Print summary
    print(f"\n{'='*70}")
    gate_status = "ALL PASS" if all_gates_pass else "GATE FAILED"
    print(f"  评测完成: {pass_count}/{total} 通过 ({pass_rate:.1f}%)  [{gate_status}]")
    print(f"  报告已保存: {output_path}")
    print(f"{'='*70}")
    print(f"\n  质量门槛:")
    print(f"    overall  >= {gate_overall:>2}%  actual {pass_rate:.1f}%  {'PASS' if gates_passed['overall_80'] else 'FAIL'}")
    print(f"    hard     >= {gate_hard:>2}%  actual {hard_pass_rate:.1f}%  {'PASS' if gates_passed['hard_75'] else 'FAIL'}")
    print(f"    critical >= {gate_cr:>2}%  actual {cr_pass_rate:.1f}%  {'PASS' if gates_passed['critical_95'] else 'FAIL'}  ({cr_pass}/{cr_total} rules)")
    print(f"\n  分类明细:")
    for cat, stat in by_category.items():
        rate = stat["pass"] / stat["total"] * 100 if stat["total"] > 0 else 0
        print(f"    {cat:<22} {stat['pass']}/{stat['total']} ({rate:.0f}%)")
    print(f"\n  难度明细:")
    for diff in ["easy", "medium", "hard"]:
        if diff in by_difficulty:
            stat = by_difficulty[diff]
            rate = stat["pass"] / stat["total"] * 100 if stat["total"] > 0 else 0
            print(f"    {diff:<22} {stat['pass']}/{stat['total']} ({rate:.0f}%)")
    if attributions:
        print(f"\n  失败归因:")
        for attr, count in sorted(attributions.items(), key=lambda x: -x[1]):
            print(f"    {attr:<40} {count} 条")
    print()

    return report


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Chain-AskData 黄金评测集 runner")
    parser.add_argument("--api", default=DEFAULT_API, help=f"API base URL (default: {DEFAULT_API})")
    parser.add_argument("--eval-set", default=str(EVAL_SET_PATH), help=f"评测集 JSON 路径 (default: {EVAL_SET_PATH})")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="输出报告路径")
    parser.add_argument("--filter", default="", help="只跑指定类别 (逗号分隔, 如 standard,synonym_rewrite)")
    parser.add_argument("--ids", default="", help="只跑指定 ID (逗号分隔, 如 EVAL_001,EVAL_008)")
    args = parser.parse_args()

    filter_categories = [c.strip() for c in args.filter.split(",") if c.strip()] or None
    filter_ids = [i.strip() for i in args.ids.split(",") if i.strip()] or None

    run_eval(
        api_base=args.api,
        eval_set_path=Path(args.eval_set),
        output_path=Path(args.output),
        filter_categories=filter_categories,
        filter_ids=filter_ids,
    )


if __name__ == "__main__":
    main()
