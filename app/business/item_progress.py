"""Helpers for item-level monthly target progress SQL."""

from __future__ import annotations

import re


ITEM_INCOME_PROGRESS_METRIC = "item_execution_income_time_progress_rate"
ITEM_INCOME_PROGRESS_TEMPLATE = "item_income_progress_mtd"

KNOWN_ITEM_NAMES = (
    "奇迹胶原",
    "奇迹童颜",
    "新一代热玛吉",
    "热玛吉",
    "BBL HERO",
    "BBL",
    "爱拉丝提",
    "漾活光彩针",
    "玻尿酸",
    "肉毒",
    "水光微针",
    "小光电",
    "胶原蛋白",
    "薇旖美",
)

_PROGRESS_TERMS = ("时间进度", "进度达成率", "达成率", "进度完成率")
_NOISE_PREFIXES = ("本月", "当月", "这个月", "请问", "帮我查", "帮我算", "查询")
_NOISE_SUFFIXES = ("的", "是多少", "多少", "？", "?", "呢")


def is_item_income_progress_question(question: str) -> bool:
    q = question or ""
    return "核销收入" in q and any(term in q for term in _PROGRESS_TERMS)


def extract_item_name(question: str) -> str:
    """Extract the item keyword from an item progress question.

    Prefer explicit known item names. Fall back to a conservative pattern for
    questions like "本月奇迹童颜核销收入时间进度达成率".
    """
    q = (question or "").strip()
    for item_name in KNOWN_ITEM_NAMES:
        if item_name in q:
            return item_name

    patterns = (
        r"(?:本月|当月|这个月)?(.+?)核销收入(?:时间进度|进度达成率|达成率|进度完成率)",
        r"(?:本月|当月|这个月)?(.+?)的?核销收入(?:时间进度|进度达成率|达成率|进度完成率)",
    )
    for pattern in patterns:
        match = re.search(pattern, q)
        if match:
            candidate = _clean_item_name(match.group(1))
            if candidate:
                return candidate
    return ""


def item_income_progress_sql(item_name: str) -> str:
    item = _sql_literal(extract_item_name(item_name) or item_name or "奇迹胶原")
    return f"""WITH actual_income AS (
    SELECT  DATE_FORMAT(CAST(CURRENT_DATE() AS TIMESTAMP), 'yyyy-MM') AS month,
            '{item}' AS standard_name,
            COALESCE(SUM(exe_income), 0) AS actual_exe_income
    FROM    soyoung_dw.dm_opt_qy_user_execution_record_all_d
    WHERE   dp = DATE_SUB(CURRENT_DATE(), 1)
    AND     is_valid = 1
    AND     standard_name REGEXP '{item}'
    AND     executed_date BETWEEN DATE_FORMAT(CAST(CURRENT_DATE() AS TIMESTAMP), 'yyyy-MM-01')
                              AND DATE_SUB(CURRENT_DATE(), 1)
),
target_income AS (
    SELECT  month,
            third_level_hierarchy AS standard_name,
            SUM(target_absolute_value) AS target_exe_income
    FROM    soyoung_dw.dim_channel_month_income_target
    WHERE   month = DATE_FORMAT(CAST(CURRENT_DATE() AS TIMESTAMP), 'yyyy-MM')
    AND     first_level_hierarchy = '货'
    AND     second_level_hierarchy = '大单品'
    AND     third_level_hierarchy REGEXP '{item}'
    AND     fourth_level_hierarchy = '整体'
    AND     target_type = '收入'
    GROUP BY month, third_level_hierarchy
)
SELECT  a.actual_exe_income,
        t.target_exe_income,
        DAY(DATE_SUB(CURRENT_DATE(), 1)) AS elapsed_days,
        DAY(LAST_DAY(CURRENT_DATE())) AS month_days,
        a.actual_exe_income / NULLIF(t.target_exe_income, 0) AS target_completion_rate,
        1.0 * DAY(DATE_SUB(CURRENT_DATE(), 1)) / NULLIF(DAY(LAST_DAY(CURRENT_DATE())), 0) AS time_progress_rate,
        (a.actual_exe_income / NULLIF(t.target_exe_income, 0))
        / NULLIF(1.0 * DAY(DATE_SUB(CURRENT_DATE(), 1)) / NULLIF(DAY(LAST_DAY(CURRENT_DATE())), 0), 0) AS time_progress_achievement_rate
FROM    actual_income a
LEFT JOIN target_income t
       ON  a.month = t.month
       AND a.standard_name = t.standard_name;"""


def _clean_item_name(value: str) -> str:
    candidate = value.strip()
    for prefix in _NOISE_PREFIXES:
        if candidate.startswith(prefix):
            candidate = candidate[len(prefix):].strip()
    for suffix in _NOISE_SUFFIXES:
        if candidate.endswith(suffix):
            candidate = candidate[: -len(suffix)].strip()
    return candidate if _is_safe_item_token(candidate) else ""


def _is_safe_item_token(value: str) -> bool:
    if not value or len(value) > 40:
        return False
    return bool(re.fullmatch(r"[\u4e00-\u9fffA-Za-z0-9·\-\s]+", value))


def _sql_literal(value: str) -> str:
    raw = value.strip()
    cleaned = _clean_item_name(raw) or (raw if _is_safe_item_token(raw) else "奇迹胶原")
    return cleaned.replace("'", "''")
