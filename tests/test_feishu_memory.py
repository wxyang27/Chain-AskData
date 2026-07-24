import asyncio
from types import SimpleNamespace

from app.core.config import settings
from app.execution.factory import create_sql_executor
from app.feishu_bot.runner import (
    CatDataFeishuBot,
    build_feishu_session_id,
    configure_feishu_pipeline,
    extract_question_from_quoted_message,
    _extract_parent_message_id,
)
from app.memory.objects import ConversationState
from app.memory.rewriter import QuestionRewriter
from app.memory.store import get_default_memory_store
from app.models.query import QueryPlan, QueryResponse, ValidationResult


class FakeMessage:
    message_id = "om_test"
    chat_id = "oc_group"
    sender_id = "ou_user"
    chat_type = "group"
    mentioned_bot = True
    sender_is_bot = False
    body_text = "本月华东大区支付GMV"
    content_text = ""
    raw = {}


class FakeComposer:
    def __init__(self) -> None:
        self.calls = []
        self.pipeline = SimpleNamespace(question_rewriter=QuestionRewriter())

    def compose(
        self,
        question: str,
        *,
        session_id: str = "",
        use_memory: bool = True,
        memory_states_override=None,
    ) -> QueryResponse:
        self.calls.append(
            {
                "question": question,
                "session_id": session_id,
                "use_memory": use_memory,
                "memory_states_override": memory_states_override,
            }
        )
        return QueryResponse(
            project="Chain-AskData",
            question_summary=f"你想查询：{question}",
            original_question=question,
            resolved_question=question,
            session_id=session_id,
            memory_used=False,
            memory_resolution={"memory_window_size": 0},
            query_plan=QueryPlan(
                intent="nl2sql",
                business_domain="chain",
                original_question=question,
                template_id="payment_gmv_summary_30d",
                metrics=[],
            ),
            sql="SELECT 1;",
            validation=ValidationResult(passed=True),
            caliber_notes=[],
            sql_source="template",
            execution_enabled=False,
            execution_mode="disabled",
            execution_status="skipped",
        )


class FakeLogger:
    def __init__(self) -> None:
        self.entries = []

    def write(self, entry) -> None:
        self.entries.append(entry)


class FakeLlmComponent:
    enabled = True


class FakePlanner:
    def __init__(self) -> None:
        self.llm_cot_generator = FakeLlmComponent()


class FakePipeline:
    def __init__(self) -> None:
        self.planner = FakePlanner()
        self.llm_sql_generator = FakeLlmComponent()
        self.executor = create_sql_executor("mock")


class FakePipelineComposer:
    def __init__(self) -> None:
        self.pipeline = FakePipeline()


def _bot_with_fakes() -> tuple[CatDataFeishuBot, FakeComposer, list[tuple]]:
    bot = object.__new__(CatDataFeishuBot)
    composer = FakeComposer()
    replies = []
    bot.composer = composer
    bot.base_logger = FakeLogger()
    bot._sender_name_cache = {}
    bot._message_context_by_id = {}
    bot._tenant_access_token = ""
    bot._tenant_access_token_expires_at = 0.0

    async def fake_reply(message, text, card=None):
        replies.append((message, text, card))

    async def fake_resolve_sender_name(message, sender_id):
        return "Soyoung"

    bot._reply = fake_reply
    bot._resolve_sender_name = fake_resolve_sender_name
    return bot, composer, replies


def test_feishu_session_id_is_scoped_by_chat_and_sender():
    assert build_feishu_session_id(FakeMessage()) == "feishu:oc_group:ou_user"


def test_feishu_pipeline_applies_feishu_llm_setting_and_disabled_execution():
    composer = FakePipelineComposer()

    configure_feishu_pipeline(composer)

    assert composer.pipeline.planner.llm_cot_generator.enabled is settings.feishu_llm_enabled
    assert composer.pipeline.llm_sql_generator.enabled is settings.feishu_llm_enabled
    assert composer.pipeline.executor.enabled is False
    assert composer.pipeline.executor.mode == "disabled"


def test_feishu_message_passes_session_id_and_enables_memory():
    bot, composer, replies = _bot_with_fakes()

    asyncio.run(bot.on_message(FakeMessage()))

    assert composer.calls == [
        {
            "question": "本月华东大区支付GMV",
            "session_id": "feishu:oc_group:ou_user",
            "use_memory": True,
            "memory_states_override": None,
        }
    ]
    assert len(replies) == 2


def test_feishu_clear_memory_command_clears_current_session():
    message = FakeMessage()
    message.body_text = "清空记忆"
    session_id = build_feishu_session_id(message)
    store = get_default_memory_store()
    store.save(
        ConversationState(
            session_id=session_id,
            last_resolved_question="本月华东大区支付GMV",
        )
    )
    bot, composer, replies = _bot_with_fakes()

    asyncio.run(bot.on_message(message))

    assert composer.calls == []
    assert store.get_window(session_id) == []
    assert replies[-1][1].startswith("已清空当前飞书会话")


def test_extract_question_from_quoted_card_title():
    content = (
        '{"schema":"2.0","header":{"title":{"tag":"plain_text",'
        '"content":"本周华北大区核销收入"},"template":"default"},'
        '"body":{"elements":[{"tag":"markdown","content":"已生成 SQL"}]}}'
    )

    assert extract_question_from_quoted_message(content) == "本周华北大区核销收入"


def test_extract_question_from_quoted_markdown_answer():
    content = '{"text":"**我查了一下：本周华北大区核销收入**\\n已生成 SQL。"}'

    assert extract_question_from_quoted_message(content) == "本周华北大区核销收入"


def test_feishu_reply_uses_quoted_message_as_memory_base():
    message = FakeMessage()
    message.body_text = "那华中大区呢"
    message.parent_id = "om_parent"
    bot, composer, replies = _bot_with_fakes()

    async def fake_fetch_message_content(message_id):
        assert message_id == "om_parent"
        return '{"text":"**我查了一下：本周华北大区核销收入**\\n已生成 SQL。"}'

    bot._fetch_message_content = fake_fetch_message_content

    asyncio.run(bot.on_message(message))

    override = composer.calls[0]["memory_states_override"]
    assert composer.calls[0]["question"] == "那华中大区呢"
    assert override is not None
    assert override[0].last_resolved_question == "本周华北大区核销收入"
    assert len(replies) == 2


def test_extract_parent_message_id_reads_sdk_reply_ref():
    class Reply:
        message_id = "om_reply_parent"

    message = FakeMessage()
    message.reply = Reply()

    assert _extract_parent_message_id(message) == "om_reply_parent"


def test_feishu_reply_uses_sdk_quoted_context():
    class Reply:
        message_id = "om_sdk_parent"

    class FakeChannel:
        async def fetch_quoted_context(self, message_id):
            assert message_id == "om_sdk_parent"
            return SimpleNamespace(text="本周北京奇迹胶原核销收入TOP5门店")

    message = FakeMessage()
    message.body_text = "那top3呢"
    message.reply = Reply()
    bot, composer, _ = _bot_with_fakes()
    bot.channel = FakeChannel()

    asyncio.run(bot.on_message(message))

    override = composer.calls[0]["memory_states_override"]
    assert override is not None
    assert override[0].last_resolved_question == "本周北京奇迹胶原核销收入TOP5门店"


def test_feishu_reply_prefers_local_sent_message_context():
    class Reply:
        message_id = "om_bot_answer"

    message = FakeMessage()
    message.body_text = "那top3呢"
    message.reply = Reply()
    bot, composer, _ = _bot_with_fakes()
    bot._message_context_by_id["om_bot_answer"] = "本周北京奇迹胶原核销收入TOP5门店"

    asyncio.run(bot.on_message(message))

    override = composer.calls[0]["memory_states_override"]
    assert override is not None
    assert override[0].last_resolved_question == "本周北京奇迹胶原核销收入TOP5门店"
