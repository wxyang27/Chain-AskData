from __future__ import annotations

import html
import re
from decimal import Decimal, InvalidOperation
from typing import Any

from app.feishu_bot.formatter import (
    BOT_BOUNDARY_TEXT,
    BOT_EXAMPLES,
    BOT_SCOPE_TEXT,
    _clip,
)
from app.models.query import QueryResponse


Card = dict[str, Any]


def build_processing_card(question: str) -> Card:
    return _base_card(
        title="CatData",
        subtitle="正在查询连锁经营数据",
        tag_text="处理中",
        body=[
            _plain_markdown(
                "**收到，正在查询**\n"
                f"{_md(_clip(question, 120))}\n"
                "<font color='grey'>稍等一下，结果会直接回复在这里。</font>"
            )
        ],
        header_template="default",
    )


def build_query_card(response: QueryResponse) -> Card:
    question = response.query_plan.original_question or response.question_summary
    success = response.execution_status == "success"
    tag_text = "查询完成" if success else "查询异常"
    subtitle = f"{response.execution_mode} · {response.sql_source}"

    elements: list[Card] = []
    status_text = _status_text(response)
    if status_text:
        elements.append(_plain_markdown(status_text))

    if response.sample_rows:
        elements.extend(_result_blocks(response.sample_rows[:5]))

    if response.sql:
        elements.append(_sql_block(response.sql))

    return _base_card(
        title=_one_line(question, 42),
        subtitle=subtitle,
        tag_text=tag_text,
        tag_color="green" if success else "red",
        body=elements,
    )


def build_greeting_card() -> Card:
    return _bot_info_card("CatData 可以帮你查什么", BOT_SCOPE_TEXT)


def build_help_card() -> Card:
    return _bot_info_card("CatData 使用示例", BOT_SCOPE_TEXT)


def build_unsupported_card(question: str) -> Card:
    return _bot_info_card(
        "这个问题不在问数范围内",
        f"你刚才问：{_md(_clip(question, 120))}\n\n{BOT_BOUNDARY_TEXT}",
        tag_text="无法回答",
        tag_color="yellow",
    )


def build_error_card(question: str, error: Exception) -> Card:
    detail = _clip(str(error), 500)
    return _base_card(
        title="CatData 查询失败",
        subtitle="请稍后重试或在本地接口验证",
        tag_text="失败",
        tag_color="red",
        body=[
            _notice_block(f"**问题**\n{_md(_clip(question, 160))}", color="red"),
            _notice_block(f"**错误信息**\n{_md(detail)}", color="grey"),
        ],
    )


def _bot_info_card(title: str, intro: str, tag_text: str = "帮助", tag_color: str = "green") -> Card:
    examples = "\n".join(f"- {_md(line[2:])}" for line in BOT_EXAMPLES.splitlines() if line.startswith("- "))
    return _base_card(
        title=title,
        subtitle="新氧连锁经营数据问数助手",
        tag_text=tag_text,
        tag_color=tag_color,
        body=[
            _notice_block(_md(intro)),
            _notice_block("**你可以这样问**\n" + examples, color="grey"),
        ],
    )


def _base_card(
    *,
    title: str,
    subtitle: str,
    tag_text: str,
    body: list[Card],
    tag_color: str = "green",
    header_template: str = "green",
) -> Card:
    return {
        "schema": "2.0",
        "config": {
            "update_multi": True,
            "width_mode": "default",
            "summary": {"content": title},
            "style": {
                "text_size": {
                    "title": {"default": "heading-2", "pc": "heading-2", "mobile": "heading-3"},
                    "body": {"default": "normal", "pc": "normal", "mobile": "normal"},
                    "caption": {"default": "notation", "pc": "notation", "mobile": "notation"},
                },
                "color": {
                    "cat-green": {
                        "light_mode": "rgba(18,128,64,1)",
                        "dark_mode": "rgba(80,190,120,1)",
                    },
                    "cat-muted": {
                        "light_mode": "rgba(100,106,115,1)",
                        "dark_mode": "rgba(150,155,163,1)",
                    },
                },
            },
        },
        "header": {
            "title": {"tag": "plain_text", "content": title},
            "subtitle": {"tag": "plain_text", "content": subtitle},
            "template": header_template,
            "text_tag_list": [
                {
                    "tag": "text_tag",
                    "text": {"tag": "plain_text", "content": tag_text},
                    "color": tag_color,
                }
            ],
        },
        "body": {
            "direction": "vertical",
            "padding": "12px 12px 16px 12px",
            "vertical_spacing": "10px",
            "elements": body,
        },
    }


def _summary_metrics(response: QueryResponse) -> Card:
    status = "成功" if response.execution_status == "success" else response.execution_status
    fields = [
        ("结果行数", str(response.row_count)),
        ("执行模式", response.execution_mode or "unknown"),
        ("SQL 来源", response.sql_source or "unknown"),
        ("状态", status or "unknown"),
    ]
    return {
        "tag": "div",
        "fields": [
            {
                "is_short": True,
                "text": {
                    "tag": "lark_md",
                    "content": f"**{_md(label)}**\n<font color='green'>{_md(_one_line(value, 40))}</font>",
                },
            }
            for label, value in fields
        ],
    }


def _status_text(response: QueryResponse) -> str:
    if response.execution_enabled:
        if response.execution_status == "success":
            return (
                f"**已查到 {response.row_count} 条结果**\n"
                f"<font color='grey'>{_md(response.execution_mode or 'unknown')} · "
                f"{_md(response.sql_source or 'unknown')}</font>"
            )
        if response.execution_error:
            return f"**查询执行异常**\n{_md(_clip(response.execution_error, 500))}"
        return f"**查询执行状态：** {_md(response.execution_status)}"

    return "**已生成 SQL，当前没有执行真实查询。**"


def _result_blocks(rows: list[dict[str, Any]]) -> list[Card]:
    keys = _select_columns(rows)
    if len(keys) >= 2 and _column_type(rows, keys[1]) == "number":
        return [_ranking_chart(rows, keys[0], keys[1]), _ranking_list(rows, keys[0], keys[1])]
    return [_result_table(rows)]


def _ranking_chart(rows: list[dict[str, Any]], label_key: str, value_key: str) -> Card:
    values = []
    for idx, row in enumerate(rows, start=1):
        value = _number_value(row.get(value_key))
        if value is None:
            continue
        full_name = str(row.get(label_key, "") or "")
        name = _chart_label(full_name, idx)
        values.append(
            {
                "rank": idx,
                "name": f"{idx}. {name}",
                "value": round(value, 4),
            }
        )

    if not values:
        return _ranking_list(rows, label_key, value_key)

    height = min(320, max(200, 42 * len(values) + 72))
    return {
        "tag": "chart",
        "element_id": "ranking_chart",
        "aspect_ratio": "4:3",
        "color_theme": "brand",
        "height": f"{height}px",
        "preview": True,
        "chart_spec": {
            "type": "bar",
            "data": {"values": values},
            "direction": "horizontal",
            "xField": "value",
            "yField": "name",
            "bar": {
                "style": {
                    "fill": "#2E9E6F",
                }
            },
            "label": {
                "visible": True,
                "position": "right",
                "style": {
                    "fill": "#137333",
                    "fontWeight": 600,
                },
            },
            "axes": [
                {
                    "orient": "bottom",
                    "grid": {"visible": False},
                    "label": {"style": {"fill": "#8F959E"}},
                },
                {
                    "orient": "left",
                    "label": {"style": {"fill": "#4E5969", "fontSize": 12}},
                },
            ],
        },
    }


def _ranking_list(rows: list[dict[str, Any]], label_key: str, value_key: str) -> Card:
    lines = ["**门店明细**"]
    for idx, row in enumerate(rows, start=1):
        label = _one_line(row.get(label_key, ""), 52)
        value = _format_number(row.get(value_key))
        lines.append(f"{idx}. {_md(label)}  <font color='green'>{_md(value)}</font>")
    return {
        "tag": "markdown",
        "content": "\n".join(lines),
        "text_size": "normal",
    }


def _result_table(rows: list[dict[str, Any]]) -> Card:
    keys = _select_columns(rows)
    columns = [
        {
            "name": f"c{idx}",
            "display_name": _display_name(key),
            "data_type": _column_type(rows, key),
            "width": "62%" if idx == 0 else "auto",
            "horizontal_align": "left" if idx == 0 else "right",
        }
        for idx, key in enumerate(keys)
    ]
    table_rows = []
    for row in rows:
        table_rows.append({f"c{idx}": _cell_value(row.get(key)) for idx, key in enumerate(keys)})
    return {
        "tag": "table",
        "columns": columns,
        "rows": table_rows,
        "page_size": min(max(len(table_rows), 1), 5),
        "row_height": "middle",
        "row_max_height": "72px",
        "freeze_first_column": True,
        "header_style": {
            "background_style": "grey",
            "bold": True,
            "lines": 1,
        },
    }


def _plain_markdown(content: str) -> Card:
    return {
        "tag": "markdown",
        "content": content,
        "text_size": "normal",
    }


def _sql_block(sql: str) -> Card:
    formatted_sql = _format_sql_for_card(sql)
    return {
        "tag": "collapsible_panel",
        "expanded": False,
        "header": {
            "title": {"tag": "plain_text", "content": "SQL"},
            "background_color": "grey-50",
        },
        "padding": "8px",
        "border": {"color": "grey-200", "corner_radius": "6px"},
        "elements": [
            {
                "tag": "markdown",
                "content": "```sql\n" + _clip(formatted_sql, 3200) + "\n```",
                "text_size": "notation",
            }
        ],
    }


def _notice_block(content: str, color: str = "green") -> Card:
    return {
        "tag": "column_set",
        "flex_mode": "none",
        "columns": [
            {
                "tag": "column",
                "width": "weighted",
                "weight": 1,
                "background_style": f"{color}-50",
                "padding": "12px",
                "vertical_spacing": "4px",
                "elements": [
                    {
                        "tag": "markdown",
                        "content": content,
                        "text_size": "normal",
                    }
                ],
            }
        ],
    }


def _select_columns(rows: list[dict[str, Any]]) -> list[str]:
    keys: list[str] = []
    for row in rows:
        for key in row.keys():
            if key not in keys:
                keys.append(key)
    return keys[:4] or ["结果"]


def _display_name(key: str) -> str:
    mapping = {
        "sy_hospital_name": "门店",
        "hospital_name": "门店",
        "tenant_name": "门店",
        "store_name": "门店",
        "total_income": "核销收入",
        "exe_income": "核销收入",
        "exe_amount": "核销GMV",
        "pay_amount": "支付金额",
        "pay_income": "支付收入",
        "cnt": "数量",
        "count": "数量",
    }
    return mapping.get(key, key)


def _column_type(rows: list[dict[str, Any]], key: str) -> str:
    for row in rows:
        value = row.get(key)
        if value is not None:
            return "number" if _number_value(value) is not None else "text"
    return "text"


def _cell_value(value: Any) -> Any:
    if value is None:
        return ""
    number = _number_value(value)
    if number is not None:
        return round(number, 4)
    return _clip(str(value), 120)


def _format_number(value: Any) -> str:
    number = _number_value(value)
    if number is not None:
        return f"{number:,.2f}"
    return _one_line(value, 32)


def _number_value(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float, Decimal)):
        return float(value)
    if isinstance(value, str):
        text = value.strip().replace(",", "")
        if not text:
            return None
        try:
            return float(Decimal(text))
        except (InvalidOperation, ValueError):
            return None
    return None


def _chart_label(text: str, fallback_rank: int) -> str:
    match = re.search(r"\bNo\.\s*\d+\b", text, flags=re.IGNORECASE)
    if match:
        return match.group(0).replace(" ", "")
    return _one_line(text, 18) or f"TOP{fallback_rank}"


def _format_sql_for_card(sql: str) -> str:
    value = _normalize_sql_whitespace(sql.strip().rstrip(";"))
    if not value:
        return ""

    keyword_patterns = [
        r"UNION\s+ALL",
        r"LEFT\s+JOIN",
        r"RIGHT\s+JOIN",
        r"INNER\s+JOIN",
        r"FULL\s+JOIN",
        r"GROUP\s+BY",
        r"ORDER\s+BY",
        r"SELECT",
        r"FROM",
        r"WHERE",
        r"HAVING",
        r"LIMIT",
        r"ON",
        r"AND",
        r"OR",
    ]
    for pattern in keyword_patterns:
        value = re.sub(rf"\s+\b({pattern})\b", r"\n\1", value, flags=re.IGNORECASE)
    value = re.sub(
        r"(?<!LEFT)(?<!RIGHT)(?<!INNER)(?<!FULL)\s+\b(JOIN)\b",
        r"\n\1",
        value,
        flags=re.IGNORECASE,
    )

    value = _break_top_level_commas(value)
    lines = []
    for raw_line in value.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        upper = line.upper()
        if upper.startswith(("ON ", "AND ", "OR ")):
            line = "  " + line
        elif lines and not upper.startswith(
            (
                "SELECT",
                "FROM",
                "LEFT JOIN",
                "RIGHT JOIN",
                "INNER JOIN",
                "FULL JOIN",
                "JOIN",
                "WHERE",
                "GROUP BY",
                "ORDER BY",
                "HAVING",
                "LIMIT",
                "UNION",
            )
        ):
            line = "    " + line
        lines.extend(_wrap_sql_line(line, width=96))
    return "\n".join(lines) + ";"


def _normalize_sql_whitespace(sql: str) -> str:
    result: list[str] = []
    quote: str | None = None
    pending_space = False

    for char in sql:
        if quote:
            result.append(char)
            if char == quote:
                quote = None
            continue
        if char in {"'", '"', "`"}:
            if pending_space and result:
                result.append(" ")
                pending_space = False
            quote = char
            result.append(char)
            continue
        if char.isspace():
            pending_space = True
            continue
        if pending_space and result:
            result.append(" ")
        pending_space = False
        result.append(char)
    return "".join(result).strip()


def _break_top_level_commas(sql: str) -> str:
    result: list[str] = []
    quote: str | None = None
    depth = 0
    for char in sql:
        if quote:
            result.append(char)
            if char == quote:
                quote = None
            continue
        if char in {"'", '"', "`"}:
            quote = char
            result.append(char)
            continue
        if char == "(":
            depth += 1
        elif char == ")" and depth > 0:
            depth -= 1
        if char == "," and depth == 0:
            result.append(",\n")
            continue
        result.append(char)
    return "".join(result)


def _wrap_sql_line(line: str, width: int) -> list[str]:
    if len(line) <= width:
        return [line]

    indent = line[: len(line) - len(line.lstrip())]
    wrapped: list[str] = []
    current = line
    continuation_indent = indent + "    "
    while len(current) > width:
        split_at = current.rfind(" ", 0, width)
        if split_at <= len(indent):
            split_at = width
        wrapped.append(current[:split_at].rstrip())
        current = continuation_indent + current[split_at:].strip()
    if current.strip():
        wrapped.append(current)
    return wrapped


def _md(text: str) -> str:
    return html.escape(str(text or ""), quote=False)


def _one_line(text: str, max_chars: int) -> str:
    value = " ".join(str(text or "").split())
    if len(value) <= max_chars:
        return value
    return value[: max_chars - 1].rstrip() + "…"
