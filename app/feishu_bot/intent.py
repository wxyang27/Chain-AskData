import re
from dataclasses import dataclass
from typing import Literal


BotIntent = Literal["greeting", "help", "data_query", "unsupported"]


@dataclass(frozen=True)
class BotIntentResult:
    intent: BotIntent
    reason: str = ""


GREETING_TERMS = {
    "hi",
    "hello",
    "hey",
    "你好",
    "您好",
    "哈喽",
    "嗨",
    "在吗",
    "在不在",
    "test",
    "测试",
}

HELP_TERMS = {"help", "帮助", "怎么用", "你能做什么", "示例", "demo"}

DATA_TERMS = {
    "核销",
    "支付",
    "收入",
    "gmv",
    "门店",
    "品项",
    "项目",
    "渠道",
    "新客",
    "老客",
    "私域",
    "公域",
    "待核销",
    "客单价",
    "人次",
    "人数",
    "top",
    "排行",
    "排名",
    "达成率",
    "渗透率",
    "0元单",
    "升单",
    "北京",
    "上海",
    "广州",
    "深圳",
}

QUERY_ACTION_TERMS = {
    "查",
    "查询",
    "看看",
    "看下",
    "统计",
    "对比",
    "多少",
    "是多少",
    "列出",
    "给我",
    "最近",
    "昨天",
    "本月",
    "本周",
    "截至",
}


def classify_bot_intent(text: str) -> BotIntentResult:
    normalized = text.strip().lower()
    compact = re.sub(r"\s+", "", normalized)

    if not compact:
        return BotIntentResult("help", "empty")

    if compact in GREETING_TERMS:
        return BotIntentResult("greeting", "short_greeting")

    if compact in HELP_TERMS or any(term in compact for term in HELP_TERMS):
        return BotIntentResult("help", "help_request")

    has_data_term = any(term in compact for term in DATA_TERMS)
    has_action = any(term in compact for term in QUERY_ACTION_TERMS)
    has_number_or_time = bool(re.search(r"\d|top|最近|昨天|本月|本周|今日|今天", compact))

    if has_data_term and (has_action or has_number_or_time or len(compact) >= 8):
        return BotIntentResult("data_query", "business_query")

    if has_data_term and len(compact) >= 4:
        return BotIntentResult("data_query", "business_term")

    return BotIntentResult("unsupported", "no_business_signal")
