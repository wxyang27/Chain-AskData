"""Terminal question entry for short-term memory debugging.

Usage:
    python -m app.memory_cli --session local
"""

from __future__ import annotations

import argparse

from app.answer.composer import AnswerComposer
from app.memory.store import get_default_memory_store


def main() -> None:
    parser = argparse.ArgumentParser(
        description="AskData short-term memory terminal debugger",
    )
    parser.add_argument(
        "--session",
        default="terminal",
        help="session_id used by the in-memory conversation store",
    )
    parser.add_argument(
        "--no-memory",
        action="store_true",
        help="disable follow-up completion",
    )
    args = parser.parse_args()

    composer = AnswerComposer()
    use_memory = not args.no_memory
    print(f"Chain-AskData memory CLI | session_id={args.session} | memory={use_memory}")
    print("输入问题后回车；输入 exit / quit / 退出 结束；输入 clear 清空当前会话记忆。")

    while True:
        question = input("\nAskData> ").strip()
        if not question:
            continue
        if question.lower() in {"exit", "quit"} or question == "退出":
            break
        if question.lower() == "clear" or question == "清空":
            get_default_memory_store().clear(args.session)
            print("当前会话记忆已清空。")
            continue

        response = composer.compose(
            question,
            session_id=args.session,
            use_memory=use_memory,
        )
        print(f"原始问题: {response.original_question}")
        print(f"补全问题: {response.resolved_question}")
        print(f"使用记忆: {response.memory_used}")
        print(f"窗口大小: {response.memory_resolution.get('memory_window_size', 0)}")
        print(f"继承轮次: {response.memory_resolution.get('selected_turn_id', '')}")
        delta = response.memory_resolution.get("delta") or {}
        if delta:
            print(f"delta: {delta}")
        print(f"template_id: {response.query_plan.template_id}")
        print(f"sql_source: {response.sql_source}")
        print(f"llm_generated: {response.llm_sql_detail.generated}")
        print(f"llm_gate_passed: {response.llm_sql_validation.passed}")
        if response.llm_sql_validation.errors:
            print(f"llm_gate_errors: {response.llm_sql_validation.errors}")
        print(f"execution: {response.execution_mode}/{response.execution_status}")
        print("SQL:")
        print(response.sql.strip() or "(no sql)")


if __name__ == "__main__":
    main()
