from app.core.config import settings
from app.models.query import QueryResponse


BOT_SCOPE_TEXT = (
    "我是 CatData，定位是新氧连锁经营数据问数助手，主要用于查询和解释连锁经营口径，"
    "例如核销、支付、门店、品项、渠道、新老客、待核销、达成率等数据问题。"
)

BOT_BOUNDARY_TEXT = (
    "这类问题不属于我的问数范围，我无法可靠回答。"
    "你可以换成包含时间、指标和维度的经营数据问题。"
)

BOT_EXAMPLES = (
    "可以这样问：\n"
    "- 最近30天北京奇迹胶原核销收入TOP5门店\n"
    "- 昨天整体核销收入、核销GMV、核销人次是多少\n"
    "- 截至昨天各门店待核销金额TOP10"
)


def _clip(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 20].rstrip() + "\n\n...已截断"


def _fence_sql(sql: str, max_chars: int = 1400) -> str:
    if not sql:
        return ""
    clipped = _clip(sql.strip(), max_chars)
    return f"```sql\n{clipped}\n```"


def format_query_response(response: QueryResponse, max_chars: int = 3500) -> str:
    """Build a compact Feishu-friendly answer from the verbose API response."""

    lines: list[str] = []
    question = response.query_plan.original_question or response.question_summary
    lines.append(f"**我查了一下：{question}**")

    if response.execution_enabled:
        if response.execution_status == "success":
            lines.append(f"已查到 {response.row_count} 条结果。")
        else:
            lines.append(f"查询执行状态：{response.execution_status}（{response.execution_mode}）")
        if response.execution_error:
            lines.append(f"执行错误：{response.execution_error}")
    else:
        lines.append("我先生成了 SQL，还没有执行真实查询。")

    if response.validation and not response.validation.passed:
        errors = "；".join(response.validation.errors[:3])
        lines.append(f"校验未通过：{errors or '未提供错误详情'}")

    if response.sample_rows:
        lines.append("")
        lines.append("结果前几名：")
        for idx, row in enumerate(response.sample_rows[:5], start=1):
            fields = [f"{key}={value}" for key, value in list(row.items())[:6]]
            lines.append(f"{idx}. " + "，".join(fields))

    notes = _business_notes(response.caliber_notes)
    if notes:
        lines.append("")
        lines.append("口径说明：")
        for note in notes[:2]:
            lines.append(f"- {_clip(note, 180)}")

    if settings.feishu_include_sql and response.sql:
        lines.append("")
        lines.append("SQL：")
        lines.append(_fence_sql(response.sql))

    return _clip("\n".join(lines), max_chars)


def format_error(question: str, error: Exception, max_chars: int = 3500) -> str:
    detail = _clip(str(error), 800)
    text = (
        f"处理这个问题时失败了：{question}\n\n"
        f"错误：{detail}\n\n"
        "可以先在本地 Web 页或 `/api/query` 验证同一个问题，确认问数链路是否正常。"
    )
    return _clip(text, max_chars)


def normalize_question(text: str) -> str:
    return " ".join((text or "").strip().split())


def format_greeting() -> str:
    return f"{BOT_SCOPE_TEXT}\n\n{BOT_EXAMPLES}"


def format_help() -> str:
    return f"{BOT_SCOPE_TEXT}\n\n{BOT_EXAMPLES}"


def format_unsupported(text: str) -> str:
    return f"{BOT_SCOPE_TEXT}\n\n{BOT_BOUNDARY_TEXT}\n\n{BOT_EXAMPLES}"


def format_processing(text: str) -> str:
    return f"收到，我正在查询：{_clip(text, 80)}\n稍等一下，我会把结果直接回复在这里。"


def _business_notes(notes: list[str]) -> list[str]:
    skipped = ("默认模式只生成 SQL", "如设置 EXECUTION_MODE")
    return [note for note in notes if not any(token in note for token in skipped)]
