#!/usr/bin/env python
"""Short-term memory follow-up evaluation runner.

Default usage:
    python eval/run_memory_eval.py

By default this runner reads ``eval/memory_followup_eval.json`` and only runs
``priority=p0_current`` cases.  It calls ``AnswerComposer`` directly with an
isolated session_id per case, so uvicorn does not need to be running.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

EVAL_SET_PATH = Path(__file__).parent / "memory_followup_eval.json"
DEFAULT_OUTPUT = (
    Path(__file__).parent
    / f"memory_eval_result_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
)


def _normalize_sql(text: str) -> str:
    value = str(text or "").lower()
    value = re.sub(r"\s+", " ", value).strip()
    value = re.sub(r"\s*([(),=<>+\-*/])\s*", r"\1", value)
    value = re.sub(r"\b(?!soyoung_dw\b)[a-zA-Z_][\w]{0,12}\.", "", value)
    return re.sub(r"\s+", "", value)


def _contains(sql: str, pattern: str) -> bool:
    return _normalize_sql(pattern) in _normalize_sql(sql)


def _all_contains(sql: str, patterns: list[str]) -> bool:
    return all(_contains(sql, pattern) for pattern in patterns)


def _any_group_contains(sql: str, groups: list[list[str]]) -> bool:
    if not groups:
        return True
    return any(_all_contains(sql, group) for group in groups)


def _response_dict(response: Any) -> dict[str, Any]:
    if hasattr(response, "model_dump"):
        return response.model_dump()
    if hasattr(response, "dict"):
        return response.dict()
    return dict(response)


def _safe_bool(value: Any) -> bool | None:
    if value is None:
        return None
    return bool(value)


def _evaluate_turn(
    *,
    case_id: str,
    turn_index: int,
    turn: dict[str, Any],
    response: Any,
) -> dict[str, Any]:
    payload = _response_dict(response)
    memory_resolution = payload.get("memory_resolution") or {}
    sql = payload.get("sql") or ""
    llm_validation = payload.get("llm_sql_validation") or {}

    checks: list[dict[str, Any]] = []

    def add(name: str, passed: bool, detail: str = "") -> None:
        checks.append({"check": name, "passed": passed, "detail": detail})

    expected_resolved = turn.get("expected_resolved")
    if expected_resolved is not None:
        actual = payload.get("resolved_question", "")
        add(
            "resolved_question",
            actual == expected_resolved,
            f"expected={expected_resolved} actual={actual}",
        )

    if "expected_memory_used" in turn:
        expected = bool(turn["expected_memory_used"])
        actual = bool(payload.get("memory_used"))
        add("memory_used", actual == expected, f"expected={expected} actual={actual}")

    if "expected_selected_turn_id" in turn:
        expected = turn["expected_selected_turn_id"]
        actual = memory_resolution.get("selected_turn_id")
        add(
            "selected_turn_id",
            actual == expected,
            f"expected={expected} actual={actual}",
        )

    required_sql_contains = turn.get("required_sql_contains") or []
    missing_required = [
        pattern for pattern in required_sql_contains if not _contains(sql, pattern)
    ]
    if required_sql_contains:
        add(
            "required_sql_contains",
            not missing_required,
            (
                f"missing={missing_required}"
                if missing_required
                else f"matched={len(required_sql_contains)}"
            ),
        )

    any_of = turn.get("required_sql_any_of") or []
    if any_of:
        add(
            "required_sql_any_of",
            _any_group_contains(sql, any_of),
            "passed" if _any_group_contains(sql, any_of) else "no group matched",
        )

    forbidden = turn.get("forbidden_sql_contains") or []
    triggered = [pattern for pattern in forbidden if _contains(sql, pattern)]
    if forbidden:
        add(
            "forbidden_sql_contains",
            not triggered,
            f"triggered={triggered}" if triggered else "none",
        )

    failed_checks = [check for check in checks if not check["passed"]]
    llm_detail = payload.get("llm_sql_detail") or {}
    llm_generated = _safe_bool(llm_detail.get("generated"))
    llm_gate_passed = (
        _safe_bool(llm_validation.get("passed"))
        if llm_generated
        else None
    )
    llm_adopted = (
        _safe_bool(payload.get("llm_sql_adopted"))
        if llm_generated
        else None
    )

    return {
        "case_id": case_id,
        "turn_index": turn_index,
        "question": turn.get("question", ""),
        "expected_resolved": expected_resolved,
        "actual_resolved": payload.get("resolved_question", ""),
        "memory_used": bool(payload.get("memory_used")),
        "selected_turn_id": memory_resolution.get("selected_turn_id"),
        "sql_source": payload.get("sql_source", ""),
        "llm_generated": llm_generated,
        "llm_gate_passed": llm_gate_passed,
        "llm_adopted": llm_adopted,
        "checks": checks,
        "passed": not failed_checks,
        "failed_checks": [check["check"] for check in failed_checks],
        "sql_preview": sql[:800],
    }


def _load_cases(path: Path, priority: str, ids: set[str] | None) -> tuple[dict, list[dict]]:
    with path.open("r", encoding="utf-8") as f:
        eval_set = json.load(f)
    cases = eval_set.get("cases", [])
    if priority != "all":
        cases = [case for case in cases if case.get("priority") == priority]
    if ids:
        cases = [case for case in cases if case.get("id") in ids]
    return eval_set.get("meta", {}), cases


def _apply_env_overrides(args: argparse.Namespace) -> None:
    if args.llm_enabled != "env":
        os.environ["LLM_ENABLED"] = "true" if args.llm_enabled == "true" else "false"
    if args.execution_mode:
        os.environ["EXECUTION_MODE"] = args.execution_mode


def run_memory_eval(
    *,
    eval_set_path: Path,
    output_path: Path,
    priority: str,
    ids: set[str] | None,
) -> dict[str, Any]:
    # Import after env overrides so app.core.config.settings sees the desired
    # LLM/execution mode for this run.
    from app.answer.composer import AnswerComposer
    from app.memory.store import get_default_memory_store

    meta, cases = _load_cases(eval_set_path, priority, ids)
    composer = AnswerComposer()
    store = get_default_memory_store()

    print()
    print("=" * 78)
    print(f"  Chain-AskData Memory Eval v{meta.get('version', '?')}")
    print(f"  cases={len(cases)} priority={priority}")
    print("=" * 78)
    print()

    case_results: list[dict[str, Any]] = []
    all_turn_results: list[dict[str, Any]] = []

    for case_index, case in enumerate(cases, start=1):
        case_id = case["id"]
        session_id = f"memory_eval:{case_id}:{datetime.now().strftime('%H%M%S%f')}"
        store.clear(session_id)
        turn_results: list[dict[str, Any]] = []

        print(f"[{case_index:>2}/{len(cases)}] {case_id} {case.get('category', '')}")

        for turn_index, turn in enumerate(case.get("turns", []), start=1):
            response = composer.compose(
                turn["question"],
                session_id=session_id,
                use_memory=True,
            )
            turn_result = _evaluate_turn(
                case_id=case_id,
                turn_index=turn_index,
                turn=turn,
                response=response,
            )
            turn_results.append(turn_result)
            all_turn_results.append(turn_result)

            status = "PASS" if turn_result["passed"] else "FAIL"
            failed = ",".join(turn_result["failed_checks"])
            print(
                f"    T{turn_index:<2} {status:<4} "
                f"memory={turn_result['memory_used']} "
                f"base={turn_result['selected_turn_id']} "
                f"source={turn_result['sql_source']}"
                + (f" failed={failed}" if failed else "")
            )

        expected_window = case.get("expected_final_window_turn_ids")
        window_check = None
        if expected_window is not None:
            actual_window = [state.turn_id for state in store.get_window(session_id)]
            window_check = {
                "expected": expected_window,
                "actual": actual_window,
                "passed": actual_window == expected_window,
            }
            status = "PASS" if window_check["passed"] else "FAIL"
            print(f"    window {status} expected={expected_window} actual={actual_window}")

        case_passed = all(turn["passed"] for turn in turn_results) and (
            window_check is None or window_check["passed"]
        )
        case_results.append(
            {
                "id": case_id,
                "priority": case.get("priority", ""),
                "category": case.get("category", ""),
                "purpose": case.get("purpose", ""),
                "passed": case_passed,
                "turns": turn_results,
                "window_check": window_check,
            }
        )

    summary = _build_summary(case_results, all_turn_results)
    report = {
        "meta": {
            "eval_set_version": meta.get("version"),
            "run_at": datetime.now().isoformat(),
            "priority": priority,
            "eval_set_path": str(eval_set_path),
        },
        "summary": summary,
        "cases": case_results,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print()
    print("=" * 78)
    print(
        "  DONE "
        f"cases={summary['passed_cases']}/{summary['total_cases']} "
        f"turns={summary['passed_turns']}/{summary['total_turns']} "
        f"resolved={summary['resolved_question_accuracy']}% "
        f"memory={summary['memory_used_accuracy']}% "
        f"selected={summary['selected_turn_accuracy']}% "
        f"sql_constraints={summary['sql_constraint_retention_rate']}%"
    )
    if summary["llm_gate_pass_rate"] is not None:
        print(
            "  LLM "
            f"gate={summary['llm_gate_pass_rate']}% "
            f"adoption={summary['llm_adoption_rate']}%"
        )
    print(f"  report={output_path}")
    print("=" * 78)
    print()

    return report


def _build_summary(
    case_results: list[dict[str, Any]],
    turn_results: list[dict[str, Any]],
) -> dict[str, Any]:
    total_cases = len(case_results)
    passed_cases = sum(1 for case in case_results if case["passed"])
    total_turns = len(turn_results)
    passed_turns = sum(1 for turn in turn_results if turn["passed"])

    def rate_for(check_name: str) -> float | None:
        relevant = [
            check
            for turn in turn_results
            for check in turn["checks"]
            if check["check"] == check_name
        ]
        if not relevant:
            return None
        passed = sum(1 for check in relevant if check["passed"])
        return round(passed / len(relevant) * 100, 1)

    sql_checks = {
        "required_sql_contains",
        "required_sql_any_of",
        "forbidden_sql_contains",
    }
    relevant_sql_checks = [
        check
        for turn in turn_results
        for check in turn["checks"]
        if check["check"] in sql_checks
    ]
    sql_rate = None
    if relevant_sql_checks:
        sql_rate = round(
            sum(1 for check in relevant_sql_checks if check["passed"])
            / len(relevant_sql_checks)
            * 100,
            1,
        )

    llm_gate_values = [
        turn["llm_gate_passed"]
        for turn in turn_results
        if turn["llm_gate_passed"] is not None
    ]
    llm_adoption_values = [
        turn["llm_adopted"]
        for turn in turn_results
        if turn["llm_adopted"] is not None
    ]

    failure_counts: dict[str, int] = {}
    for turn in turn_results:
        for failed in turn["failed_checks"]:
            failure_counts[failed] = failure_counts.get(failed, 0) + 1

    return {
        "total_cases": total_cases,
        "passed_cases": passed_cases,
        "case_pass_rate": _pct(passed_cases, total_cases),
        "total_turns": total_turns,
        "passed_turns": passed_turns,
        "turn_pass_rate": _pct(passed_turns, total_turns),
        "resolved_question_accuracy": rate_for("resolved_question"),
        "memory_used_accuracy": rate_for("memory_used"),
        "selected_turn_accuracy": rate_for("selected_turn_id"),
        "sql_constraint_retention_rate": sql_rate,
        "llm_gate_pass_rate": _bool_rate(llm_gate_values),
        "llm_adoption_rate": _bool_rate(llm_adoption_values),
        "failure_counts": failure_counts,
        "failed_cases": [
            case["id"] for case in case_results if not case["passed"]
        ],
    }


def _pct(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return round(numerator / denominator * 100, 1)


def _bool_rate(values: list[bool]) -> float | None:
    if not values:
        return None
    return round(sum(1 for value in values if value) / len(values) * 100, 1)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run Chain-AskData short-term memory follow-up eval.",
    )
    parser.add_argument(
        "--eval-set",
        default=str(EVAL_SET_PATH),
        help=f"Eval set JSON path. Default: {EVAL_SET_PATH}",
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT),
        help=f"Output report path. Default: {DEFAULT_OUTPUT}",
    )
    parser.add_argument(
        "--priority",
        default="p0_current",
        choices=["p0_current", "p1_next", "all"],
        help="Which priority bucket to run. Default: p0_current",
    )
    parser.add_argument(
        "--ids",
        default="",
        help="Comma-separated case IDs to run, e.g. MEM_P0_001,MEM_P0_002.",
    )
    parser.add_argument(
        "--llm-enabled",
        default="env",
        choices=["env", "true", "false"],
        help="Override LLM_ENABLED for this run. Default: env.",
    )
    parser.add_argument(
        "--execution-mode",
        default="disabled",
        help="Override EXECUTION_MODE. Default: disabled.",
    )
    args = parser.parse_args()

    _apply_env_overrides(args)
    ids = {item.strip() for item in args.ids.split(",") if item.strip()} or None

    run_memory_eval(
        eval_set_path=Path(args.eval_set),
        output_path=Path(args.output),
        priority=args.priority,
        ids=ids,
    )


if __name__ == "__main__":
    main()
