import asyncio
import json
import logging
import re
import time
from typing import Any

from app.answer.composer import AnswerComposer
from app.core.config import settings
from app.execution.factory import create_sql_executor
from app.feishu_bot.base_logger import FeishuBaseLogger, build_log_entry
from app.feishu_bot.cards import (
    build_error_card,
    build_greeting_card,
    build_help_card,
    build_processing_card,
    build_query_card,
    build_unsupported_card,
)
from app.feishu_bot.formatter import (
    format_error,
    format_greeting,
    format_help,
    format_processing,
    format_query_response,
    format_unsupported,
    normalize_question,
)
from app.feishu_bot.intent import classify_bot_intent
from app.memory.objects import ConversationState
from app.memory.store import get_default_memory_store

logger = logging.getLogger(__name__)


HELP_TEXT = (
    "你好，我是 CatData。你可以直接问连锁经营数据问题，例如：\n"
    "最近30天北京奇迹胶原核销收入TOP5门店"
)
MEMORY_CLEARED_TEXT = "已清空当前飞书会话的短期记忆。你可以重新开始一组追问。"


class CatDataFeishuBot:
    def __init__(self) -> None:
        if not settings.feishu_app_id or not settings.feishu_app_secret:
            raise RuntimeError("missing FEISHU_APP_ID or FEISHU_APP_SECRET in .env")

        try:
            from lark_channel import FeishuChannel, InboundConfig, PolicyConfig
        except ImportError as exc:
            raise RuntimeError(
                "lark-channel-sdk is not installed. Run: pip install -r requirements.txt"
            ) from exc

        self.composer = AnswerComposer()
        configure_feishu_pipeline(self.composer)
        self.base_logger = FeishuBaseLogger()
        self._sender_name_cache: dict[str, str] = {}
        self._message_context_by_id: dict[str, str] = {}
        self._tenant_access_token = ""
        self._tenant_access_token_expires_at = 0.0
        self.channel = FeishuChannel(
            app_id=settings.feishu_app_id,
            app_secret=settings.feishu_app_secret,
            encrypt_key=settings.feishu_encrypt_key or None,
            verification_token=settings.feishu_verification_token or None,
            policy=PolicyConfig(
                dm_policy="open",
                group_policy="open",
                require_mention=settings.feishu_group_require_mention,
                respond_to_mention_all=False,
            ),
            inbound=InboundConfig(emit_raw_events=settings.feishu_raw_event_log),
        )
        self.channel.on("message", self.on_message)
        self.channel.on("reject", self.on_reject)
        self.channel.on("error", self.on_error)
        if settings.feishu_raw_event_log:
            self.channel.on("raw", self.on_raw)
        logger.info(
            "CatData Feishu runtime: llm_enabled=%s execution_mode=%s memory_enabled=%s",
            settings.feishu_llm_enabled,
            self.composer.pipeline.executor.mode,
            settings.feishu_memory_enabled,
        )

    async def on_message(self, message) -> None:
        if getattr(message, "sender_is_bot", False):
            return

        question = normalize_question(
            getattr(message, "body_text", "") or getattr(message, "content_text", "")
        )
        if not question:
            await self._reply(message, HELP_TEXT, build_help_card())
            return

        started = time.perf_counter()
        session_id = build_feishu_session_id(message)
        log_entry = build_log_entry(message, question)
        if not log_entry.sender_name:
            log_entry.sender_name = await self._resolve_sender_name(message, log_entry.sender_id)
        logger.info(
            "CatData received Feishu question: chat_type=%s mentioned_bot=%s session_id=%s question=%s",
            getattr(message, "chat_type", ""),
            getattr(message, "mentioned_bot", False),
            session_id,
            question,
        )
        if _is_memory_clear_command(question):
            get_default_memory_store().clear(session_id)
            await self._reply(message, MEMORY_CLEARED_TEXT)
            log_entry.intent = "help"
            log_entry.status = "成功"
            log_entry.execution_mode = "unknown"
            log_entry.execution_status = "skipped"
            log_entry.elapsed_seconds = time.perf_counter() - started
            log_entry.reply_summary = MEMORY_CLEARED_TEXT
            await asyncio.to_thread(self.base_logger.write, log_entry)
            return

        intent = classify_bot_intent(question)
        log_entry.intent = intent.intent
        if intent.intent == "greeting":
            answer = format_greeting()
            await self._reply(message, answer, build_greeting_card())
            log_entry.status = "成功"
            log_entry.execution_mode = "unknown"
            log_entry.execution_status = "skipped"
            log_entry.elapsed_seconds = time.perf_counter() - started
            log_entry.reply_summary = answer
            await asyncio.to_thread(self.base_logger.write, log_entry)
            return
        if intent.intent == "help":
            answer = format_help()
            await self._reply(message, answer, build_help_card())
            log_entry.status = "成功"
            log_entry.execution_mode = "unknown"
            log_entry.execution_status = "skipped"
            log_entry.elapsed_seconds = time.perf_counter() - started
            log_entry.reply_summary = answer
            await asyncio.to_thread(self.base_logger.write, log_entry)
            return
        if intent.intent == "unsupported":
            answer = format_unsupported(question)
            await self._reply(message, answer, build_unsupported_card(question))
            log_entry.status = "已拒绝"
            log_entry.execution_mode = "unknown"
            log_entry.execution_status = "skipped"
            log_entry.elapsed_seconds = time.perf_counter() - started
            log_entry.reply_summary = answer
            await asyncio.to_thread(self.base_logger.write, log_entry)
            return

        try:
            quoted_state = await self._quoted_memory_state(message, session_id)
            memory_states_override = [quoted_state] if quoted_state else None
            preview_resolved_question = self._preview_resolved_question(
                question,
                session_id=session_id,
                memory_states_override=memory_states_override,
            )
            await self._reply(
                message,
                format_processing(question, preview_resolved_question),
                build_processing_card(question, preview_resolved_question),
            )
            response = await asyncio.to_thread(
                self.composer.compose,
                question,
                session_id=session_id,
                use_memory=settings.feishu_memory_enabled,
                memory_states_override=memory_states_override,
            )
            answer = format_query_response(response, max_chars=settings.feishu_max_reply_chars)
            answer_card = build_query_card(response)
            logger.info(
                "CatData Feishu memory resolved: session_id=%s used=%s selected_turn=%s resolved=%s",
                session_id,
                response.memory_used,
                (response.memory_resolution or {}).get("selected_turn_id", ""),
                response.resolved_question or question,
            )
            log_entry.status = "成功" if response.execution_status != "failed" else "失败"
            log_entry.execution_mode = response.execution_mode
            log_entry.execution_status = response.execution_status
            log_entry.sql_source = response.sql_source
            log_entry.row_count = response.row_count
            log_entry.sql = response.sql
            resolved_for_sent_message = response.resolved_question or response.query_plan.original_question or question
        except Exception as exc:
            logger.exception("CatData failed to answer Feishu question")
            answer = format_error(question, exc, max_chars=settings.feishu_max_reply_chars)
            answer_card = build_error_card(question, exc)
            resolved_for_sent_message = ""
            log_entry.intent = "error"
            log_entry.status = "失败"
            log_entry.execution_mode = "unknown"
            log_entry.execution_status = "failed"
            log_entry.error = str(exc)

        sent_message_id = await self._reply(message, answer, answer_card)
        if sent_message_id and resolved_for_sent_message:
            self._message_context_by_id[sent_message_id] = resolved_for_sent_message
            logger.info(
                "CatData stored message context: message_id=%s resolved_question=%s",
                sent_message_id,
                resolved_for_sent_message,
            )
        log_entry.elapsed_seconds = time.perf_counter() - started
        log_entry.reply_summary = answer
        await asyncio.to_thread(self.base_logger.write, log_entry)

    async def _reply(self, message, text: str, card: dict[str, Any] | None = None) -> str:
        if not settings.feishu_reply_enabled:
            logger.info("FEISHU_REPLY_ENABLED=false, skip reply: %s", text[:200])
            return ""

        opts = {"reply_to": message.message_id}
        if settings.feishu_card_enabled and card:
            try:
                result = await self.channel.send(message.chat_id, {"card": card}, opts)
                if getattr(result, "success", False):
                    return str(getattr(result, "message_id", "") or "")
                logger.warning("Feishu card reply failed, fallback to markdown: %s", getattr(result, "error", None))
            except Exception as exc:
                logger.warning("Feishu card reply raised, fallback to markdown: %s", exc)

        result = await self.channel.send(message.chat_id, {"markdown": text}, opts)
        return str(getattr(result, "message_id", "") or "") if getattr(result, "success", False) else ""

    async def _resolve_sender_name(self, message: Any, sender_id: str) -> str:
        name = _extract_sender_name_from_raw(getattr(message, "raw", {}) or {})
        if name:
            return name
        if not sender_id:
            return ""
        if sender_id in self._sender_name_cache:
            return self._sender_name_cache[sender_id]

        try:
            import httpx

            token = await self._get_tenant_access_token()
            if not token:
                return ""
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(
                    "https://open.feishu.cn/open-apis/contact/v3/users/batch",
                    params={"user_id_type": "open_id", "user_ids": sender_id},
                    headers={"Authorization": f"Bearer {token}"},
                )
            payload = response.json()
            user = ((payload.get("data") or {}).get("items") or [{}])[0]
            name = user.get("name") or user.get("en_name") or user.get("nickname") or ""
            if name:
                self._sender_name_cache[sender_id] = name
            return name
        except Exception as exc:
            logger.warning("Failed to resolve Feishu sender name: %s", exc)
            return ""

    async def _quoted_memory_state(
        self,
        message: Any,
        session_id: str,
    ) -> ConversationState | None:
        parent_id = _extract_parent_message_id(message)
        if not parent_id:
            return None

        stored_question = self._message_context_by_id.get(parent_id, "")
        if stored_question:
            logger.info(
                "CatData quote context hit local sent-message index: parent_id=%s quoted_question=%s",
                parent_id,
                stored_question,
            )
            return ConversationState(
                session_id=session_id,
                turn_id=0,
                last_question=stored_question,
                last_resolved_question=stored_question,
            )

        content = await self._fetch_message_content(parent_id)
        quoted_question = extract_question_from_quoted_message(content)
        if not quoted_question:
            logger.info("CatData quote context found but no question extracted: parent_id=%s", parent_id)
            return None

        logger.info(
            "CatData quote context extracted: parent_id=%s quoted_question=%s",
            parent_id,
            quoted_question,
        )
        return ConversationState(
            session_id=session_id,
            turn_id=0,
            last_question=quoted_question,
            last_resolved_question=quoted_question,
        )

    def _preview_resolved_question(
        self,
        question: str,
        *,
        session_id: str,
        memory_states_override: list[ConversationState] | None = None,
    ) -> str:
        if not settings.feishu_memory_enabled:
            return question
        state_window = (
            list(memory_states_override)
            if memory_states_override is not None
            else get_default_memory_store().get_window(session_id)
        )
        resolution = self.composer.pipeline.question_rewriter.resolve(
            question,
            state_window,
            session_id=session_id,
            enabled=True,
        )
        return resolution.resolved_question or question

    async def _fetch_message_content(self, message_id: str) -> str:
        if not message_id:
            return ""
        try:
            if hasattr(self.channel, "fetch_quoted_context"):
                context = await self.channel.fetch_quoted_context(message_id)
                text = str(getattr(context, "text", "") or "") if context else ""
                if text:
                    return text

            import httpx

            token = await self._get_tenant_access_token()
            if not token:
                return ""
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(
                    f"https://open.feishu.cn/open-apis/im/v1/messages/{message_id}",
                    params={"user_id_type": "open_id"},
                    headers={"Authorization": f"Bearer {token}"},
                )
            payload = response.json()
            items = ((payload.get("data") or {}).get("items") or [])
            if not items:
                return ""
            body = (items[0].get("body") or {}) if isinstance(items[0], dict) else {}
            return str(body.get("content") or "")
        except Exception as exc:
            logger.warning("Failed to fetch quoted Feishu message: message_id=%s error=%s", message_id, exc)
            return ""

    async def _get_tenant_access_token(self) -> str:
        now = time.time()
        if self._tenant_access_token and now < self._tenant_access_token_expires_at:
            return self._tenant_access_token

        try:
            import httpx

            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(
                    "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
                    json={
                        "app_id": settings.feishu_app_id,
                        "app_secret": settings.feishu_app_secret,
                    },
                )
            payload = response.json()
            token = payload.get("tenant_access_token", "")
            if not token:
                logger.warning("Failed to get Feishu tenant access token: %s", payload)
                return ""
            self._tenant_access_token = token
            self._tenant_access_token_expires_at = now + max(int(payload.get("expire", 7200)) - 300, 60)
            return token
        except Exception as exc:
            logger.warning("Failed to get Feishu tenant access token: %s", exc)
            return ""

    def on_reject(self, event) -> None:
        logger.info(
            "CatData ignored Feishu message: reason=%s chat_id=%s message_id=%s sender_id=%s",
            getattr(event, "reason", ""),
            getattr(event, "chat_id", ""),
            getattr(event, "message_id", ""),
            getattr(event, "sender_id", ""),
        )

    def on_error(self, error) -> None:
        logger.exception("CatData Feishu channel error: %s", error)

    def on_raw(self, data: dict) -> None:
        header = data.get("header") or {}
        event = data.get("event") or {}
        message = event.get("message") or {}
        logger.info(
            "CatData raw Feishu event: type=%s chat_type=%s message_type=%s message_id=%s",
            header.get("event_type"),
            message.get("chat_type"),
            message.get("message_type"),
            message.get("message_id"),
        )

    async def run(self) -> None:
        logger.info("Starting CatData Feishu long-connection bot")
        try:
            await self.channel.start_background(timeout=30)
            logger.info("CatData Feishu bot ready")
            while True:
                await asyncio.sleep(3600)
        finally:
            await self.channel.disconnect()


def _extract_sender_name_from_raw(raw: dict[str, Any]) -> str:
    event = raw.get("event") or {}
    candidate_paths = [
        ("sender", "sender_name"),
        ("sender", "name"),
        ("sender", "display_name"),
    ]
    for parent_key, child_key in candidate_paths:
        parent = event.get(parent_key) or {}
        value = parent.get(child_key)
        if value:
            return str(value)

    sender = event.get("sender") or {}
    sender_detail = sender.get("sender_id") or {}
    for key in ("name", "display_name", "union_id"):
        value = sender_detail.get(key)
        if value:
            return str(value)
    return ""


def configure_feishu_pipeline(composer: AnswerComposer) -> None:
    """Force Feishu runtime defaults to stable rule/template mode."""

    pipeline = composer.pipeline
    pipeline.planner.llm_cot_generator.enabled = settings.feishu_llm_enabled
    pipeline.llm_sql_generator.enabled = settings.feishu_llm_enabled
    pipeline.executor = create_sql_executor(settings.feishu_execution_mode)


def build_feishu_session_id(message: Any) -> str:
    """Build a stable memory session key for Feishu conversations.

    Group chats include sender_id to avoid different colleagues sharing one
    short-term memory window.  Private chats also keep the sender_id for a
    consistent shape across Feishu entry points.
    """

    chat_id = _safe_id(getattr(message, "chat_id", "")) or _raw_value(
        getattr(message, "raw", {}) or {},
        ("event", "message", "chat_id"),
    )
    sender_id = _safe_id(getattr(message, "sender_id", "")) or _raw_value(
        getattr(message, "raw", {}) or {},
        ("event", "sender", "sender_id", "open_id"),
        ("event", "sender", "sender_id", "user_id"),
        ("event", "sender", "sender_id", "union_id"),
    )
    parts = ["feishu"]
    if chat_id:
        parts.append(chat_id)
    if sender_id:
        parts.append(sender_id)
    if len(parts) == 1:
        message_id = _safe_id(getattr(message, "message_id", ""))
        parts.append(message_id or "unknown")
    return ":".join(parts)


def _extract_parent_message_id(message: Any) -> str:
    reply_to = _safe_id(getattr(message, "reply_to_message_id", ""))
    if reply_to:
        return reply_to

    reply = getattr(message, "reply", None)
    reply_message_id = _safe_id(getattr(reply, "message_id", "")) if reply else ""
    if reply_message_id:
        return reply_message_id

    for attr in ("parent_id", "root_id", "upper_message_id"):
        value = _safe_id(getattr(message, attr, ""))
        if value and value != _safe_id(getattr(message, "message_id", "")):
            return value

    raw = getattr(message, "raw", {}) or {}
    return _raw_value(
        raw,
        ("event", "message", "parent_id"),
        ("event", "message", "root_id"),
        ("event", "message", "upper_message_id"),
        ("event", "parent_id"),
        ("event", "root_id"),
    )


def extract_question_from_quoted_message(content: str) -> str:
    if not content:
        return ""
    text = _text_from_message_content(content)
    return _extract_question_text(text)


def _text_from_message_content(content: str) -> str:
    try:
        payload = json.loads(content)
    except (TypeError, ValueError):
        return str(content)

    if isinstance(payload, str):
        return payload
    if not isinstance(payload, dict):
        return str(content)

    if "text" in payload:
        return str(payload.get("text") or "")

    texts: list[str] = []
    header = payload.get("header") or {}
    title = header.get("title") or {}
    if isinstance(title, dict):
        texts.append(str(title.get("content") or ""))
    subtitle = header.get("subtitle") or {}
    if isinstance(subtitle, dict):
        texts.append(str(subtitle.get("content") or ""))

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            tag = node.get("tag")
            if tag in {"markdown", "plain_text", "lark_md"} and node.get("content"):
                texts.append(str(node.get("content") or ""))
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(payload.get("body") or payload.get("elements") or [])
    return "\n".join(text for text in texts if text)


def _extract_question_text(text: str) -> str:
    value = re.sub(r"<[^>]+>", "", str(text or ""))
    value = value.replace("**", "").replace("`", "")
    value = re.sub(r"\s+", " ", value).strip()
    if not value:
        return ""

    patterns = (
        r"我查了一下[:：]\s*(?P<question>[^。；;\n]+)",
        r"你想查询[:：]\s*(?P<question>[^。；;\n]+)",
        r"收到你的问题[:：]\s*(?P<question>[^。；;\n]+)",
    )
    for pattern in patterns:
        match = re.search(pattern, value)
        if match:
            return _clean_quoted_question(match.group("question"))

    first_line = value.split("\n", 1)[0].strip()
    if _looks_like_data_question(first_line):
        return _clean_quoted_question(first_line)
    return ""


def _clean_quoted_question(question: str) -> str:
    value = re.sub(r"\s+", " ", str(question or "")).strip(" ，,。；;")
    value = re.sub(r"\s+(已生成|查询完成|查询异常|SQL 生成|已执行).*$", "", value).strip(" ，,。；;")
    return value


def _looks_like_data_question(text: str) -> bool:
    if len(text) < 4 or len(text) > 80:
        return False
    has_metric = any(
        term in text
        for term in (
            "核销", "支付", "GMV", "收入", "待核销", "客单价", "人次", "人数", "订单", "服务点",
        )
    )
    has_scope = any(
        term in text
        for term in (
            "本周", "本月", "昨天", "最近", "近", "华北", "华东", "华南", "华中",
            "北京", "上海", "门店", "品项", "大区", "整体",
        )
    )
    return has_metric and has_scope


def _is_memory_clear_command(text: str) -> bool:
    compact = "".join((text or "").strip().lower().split())
    return compact in {
        "clear",
        "清空",
        "清空记忆",
        "清除记忆",
        "重置记忆",
        "清空上下文",
        "重置上下文",
        "重新开始",
    }


def _safe_id(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("open_id", "user_id", "union_id", "id"):
            if value.get(key):
                return str(value[key]).strip()
        return ""
    return str(value or "").strip()


def _raw_value(raw: dict[str, Any], *paths: tuple[str, ...]) -> str:
    for path in paths:
        current: Any = raw
        for key in path:
            if not isinstance(current, dict):
                current = None
                break
            current = current.get(key)
        value = _safe_id(current)
        if value:
            return value
    return ""


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    try:
        asyncio.run(CatDataFeishuBot().run())
    except KeyboardInterrupt:
        logger.info("CatData Feishu long-connection bot stopped")


if __name__ == "__main__":
    main()
