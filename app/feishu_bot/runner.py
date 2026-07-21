import asyncio
import logging
import time
from typing import Any

from app.answer.composer import AnswerComposer
from app.core.config import settings
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

logger = logging.getLogger(__name__)


HELP_TEXT = (
    "你好，我是 CatData。你可以直接问连锁经营数据问题，例如：\n"
    "最近30天北京奇迹胶原核销收入TOP5门店"
)


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
        self.base_logger = FeishuBaseLogger()
        self._sender_name_cache: dict[str, str] = {}
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
        log_entry = build_log_entry(message, question)
        if not log_entry.sender_name:
            log_entry.sender_name = await self._resolve_sender_name(message, log_entry.sender_id)
        logger.info(
            "CatData received Feishu question: chat_type=%s mentioned_bot=%s question=%s",
            getattr(message, "chat_type", ""),
            getattr(message, "mentioned_bot", False),
            question,
        )
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
            await self._reply(message, format_processing(question), build_processing_card(question))
            response = await asyncio.to_thread(self.composer.compose, question)
            answer = format_query_response(response, max_chars=settings.feishu_max_reply_chars)
            answer_card = build_query_card(response)
            log_entry.status = "成功" if response.execution_status != "failed" else "失败"
            log_entry.execution_mode = response.execution_mode
            log_entry.execution_status = response.execution_status
            log_entry.sql_source = response.sql_source
            log_entry.row_count = response.row_count
            log_entry.sql = response.sql
        except Exception as exc:
            logger.exception("CatData failed to answer Feishu question")
            answer = format_error(question, exc, max_chars=settings.feishu_max_reply_chars)
            answer_card = build_error_card(question, exc)
            log_entry.intent = "error"
            log_entry.status = "失败"
            log_entry.execution_mode = "unknown"
            log_entry.execution_status = "failed"
            log_entry.error = str(exc)

        await self._reply(message, answer, answer_card)
        log_entry.elapsed_seconds = time.perf_counter() - started
        log_entry.reply_summary = answer
        await asyncio.to_thread(self.base_logger.write, log_entry)

    async def _reply(self, message, text: str, card: dict[str, Any] | None = None) -> None:
        if not settings.feishu_reply_enabled:
            logger.info("FEISHU_REPLY_ENABLED=false, skip reply: %s", text[:200])
            return

        opts = {"reply_to": message.message_id}
        if settings.feishu_card_enabled and card:
            try:
                result = await self.channel.send(message.chat_id, {"card": card}, opts)
                if getattr(result, "success", False):
                    return
                logger.warning("Feishu card reply failed, fallback to markdown: %s", getattr(result, "error", None))
            except Exception as exc:
                logger.warning("Feishu card reply raised, fallback to markdown: %s", exc)

        await self.channel.send(message.chat_id, {"markdown": text}, opts)

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
