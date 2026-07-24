import json
import logging
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)


INTENT_LABELS = {
    "greeting": "问候",
    "help": "帮助",
    "data_query": "问数",
    "unsupported": "无关",
    "error": "错误",
}


FEISHU_LOG_FIELD_IDS = {
    "时间": "fldDHZ621M",
    "用户ID": "fldxpqTz6C",
    "用户名称": "fldUco9Pbj",
    "对话类型": "flda9KNpYl",
    "群聊ID": "fldItYx3od",
    "群聊名称": "fldkX1eDkL",
    "用户问题": "fldHjSpT3I",
    "意图": "fldtaHCxza",
    "回复摘要": "fldoe96P6A",
    "SQL": "fld2FixjpH",
    "SQL来源": "fldimv81jG",
    "处理状态": "fldqTTi9mW",
    "执行模式": "fld7ZlLvLv",
    "执行状态": "fldnkt6alS",
    "行数": "fldS8Pv72o",
    "耗时": "fldeNgmCiy",
    "错误信息": "fldLx5DJdW",
}


@dataclass
class FeishuLogEntry:
    message_id: str = ""
    event_id: str = ""
    chat_type: str = ""
    sender_id: str = ""
    sender_name: str = ""
    chat_id: str = ""
    chat_name: str = ""
    mentioned_bot: bool = False
    question: str = ""
    intent: str = ""
    status: str = "收到"
    execution_mode: str = "unknown"
    execution_status: str = "unknown"
    sql_source: str = ""
    row_count: int = 0
    elapsed_seconds: float = 0.0
    reply_summary: str = ""
    error: str = ""
    sql: str = ""
    created_at: datetime = field(default_factory=datetime.now)


class FeishuBaseLogger:
    fields = [
        "时间",
        "用户ID",
        "用户名称",
        "对话类型",
        "群聊ID",
        "群聊名称",
        "用户问题",
        "意图",
        "回复摘要",
        "SQL",
        "SQL来源",
        "处理状态",
        "执行模式",
        "执行状态",
        "行数",
        "耗时",
        "错误信息",
    ]

    def __init__(self) -> None:
        self.enabled = (
            settings.feishu_log_enabled
            and bool(settings.feishu_log_base_token)
            and bool(settings.feishu_log_table_id)
        )

    def write(self, entry: FeishuLogEntry) -> None:
        if not self.enabled:
            return

        body = {"fields": self._field_ids(), "rows": [self._row(entry)]}
        cmd = [
            _resolve_cli_command(settings.feishu_log_cli),
            "base",
            "+record-batch-create",
            "--base-token",
            settings.feishu_log_base_token,
            "--table-id",
            settings.feishu_log_table_id,
            "--json",
            json.dumps(body, ensure_ascii=True),
            "--as",
            settings.feishu_log_identity,
            "--format",
            "json",
        ]
        try:
            completed = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=20,
                check=False,
            )
        except Exception as exc:
            logger.warning("Failed to write CatData log to Feishu Base: %s", exc)
            return

        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "").strip()
            logger.warning("Failed to write CatData log to Feishu Base: %s", detail[:500])

    def _row(self, entry: FeishuLogEntry) -> list[Any]:
        return [
            entry.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            _clip(entry.sender_id, 500),
            _clip(entry.sender_name, 500),
            _chat_type_label(entry.chat_type),
            _clip(entry.chat_id, 500),
            _clip(entry.chat_name, 500),
            _clip(entry.question, 2000),
            INTENT_LABELS.get(entry.intent, entry.intent or "错误"),
            _clip(entry.reply_summary, 2000),
            _clip(entry.sql, 5000),
            _clip(entry.sql_source, 500),
            entry.status,
            entry.execution_mode or "unknown",
            entry.execution_status or "unknown",
            int(entry.row_count or 0),
            round(float(entry.elapsed_seconds or 0), 2),
            _clip(entry.error, 2000),
        ]

    def _field_ids(self) -> list[str]:
        return [FEISHU_LOG_FIELD_IDS.get(field, field) for field in self.fields]


def build_log_entry(message, question: str) -> FeishuLogEntry:
    return FeishuLogEntry(
        message_id=str(getattr(message, "message_id", "") or ""),
        event_id=str((getattr(message, "raw", {}) or {}).get("event_id", "") or ""),
        chat_type=str(getattr(message, "chat_type", "") or ""),
        sender_id=str(getattr(message, "sender_id", "") or ""),
        sender_name=str(getattr(message, "sender_name", "") or ""),
        chat_id=str(getattr(message, "chat_id", "") or ""),
        chat_name=str(getattr(message, "chat_name", "") or ""),
        mentioned_bot=bool(getattr(message, "mentioned_bot", False)),
        question=question,
    )


def _chat_type_label(chat_type: str) -> str:
    if chat_type == "p2p":
        return "私聊"
    return "群聊"


def _clip(value: str, max_chars: int) -> str:
    text = str(value or "")
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 8].rstrip() + "...截断"


def _resolve_cli_command(command: str) -> str:
    configured = command or "lark-cli"
    candidates = [configured]
    if os.name == "nt" and not configured.lower().endswith((".cmd", ".exe", ".bat")):
        candidates.extend([f"{configured}.cmd", f"{configured}.exe", f"{configured}.bat"])

    for candidate in candidates:
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    return configured
