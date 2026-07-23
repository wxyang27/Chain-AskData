from app.answer.composer import AnswerComposer
from app.memory.objects import ConversationState
from app.memory.rewriter import QuestionRewriter
from app.memory.store import get_default_memory_store


def test_question_rewriter_replaces_item_city_channel_time_and_topn():
    state = ConversationState(
        session_id="rewrite-case",
        last_resolved_question="最近30天北京奇迹胶原核销收入 TOP5门店",
    )
    rewriter = QuestionRewriter()

    assert rewriter.resolve(
        "那奇迹童颜呢",
        state,
        session_id=state.session_id,
    ).resolved_question == "最近30天北京奇迹童颜核销收入 TOP5门店"
    assert rewriter.resolve(
        "那上海呢",
        state,
        session_id=state.session_id,
    ).resolved_question == "最近30天上海奇迹胶原核销收入 TOP5门店"
    assert rewriter.resolve(
        "那私域呢",
        state,
        session_id=state.session_id,
    ).resolved_question == "最近30天北京奇迹胶原核销收入 TOP5门店，私域"
    assert rewriter.resolve(
        "top3",
        state,
        session_id=state.session_id,
    ).resolved_question == "最近30天北京奇迹胶原核销收入 TOP3门店"
    assert rewriter.resolve(
        "本月",
        state,
        session_id=state.session_id,
    ).resolved_question == "本月北京奇迹胶原核销收入 TOP5门店"

    area_state = ConversationState(
        session_id="rewrite-area-case",
        last_resolved_question="最近30天华北大区支付GMV是多少？",
    )
    assert rewriter.resolve(
        "那华东呢",
        area_state,
        session_id=area_state.session_id,
    ).resolved_question == "最近30天华东大区支付GMV是多少？"


def test_question_rewriter_uses_delta_for_p1_semantic_switches():
    rewriter = QuestionRewriter()

    channel_state = ConversationState(
        session_id="delta-channel",
        turn_id=1,
        last_resolved_question="最近30天私域、公域、老带新的核销收入、人次、客单价对比",
    )
    channel = rewriter.resolve("只看私域呢", channel_state, session_id="delta-channel")
    assert channel.resolved_question == "最近30天私域核销收入、人次、客单价"
    assert channel.delta is not None
    assert "channel_narrowing" in channel.delta.operations

    overall_state = ConversationState(
        session_id="delta-overall",
        turn_id=1,
        last_resolved_question="最近30天各门店核销收入 TOP10",
    )
    overall = rewriter.resolve("不要门店了，看整体", overall_state, session_id="delta-overall")
    assert overall.used_memory is True
    assert overall.resolved_question == "最近30天整体核销收入是多少？"
    assert overall.delta is not None
    assert "dimension_removal" in overall.delta.operations

    share_state = ConversationState(
        session_id="delta-share",
        turn_id=1,
        last_resolved_question="最近30天品项核销收入 TOP20",
    )
    share = rewriter.resolve("换成收入占比", share_state, session_id="delta-share")
    assert share.resolved_question == "最近30天品项核销收入占比 TOP20"
    assert share.delta is not None
    assert "metric_switch_to_ratio" in share.delta.operations

    payment_state = ConversationState(
        session_id="delta-payment",
        turn_id=1,
        last_resolved_question="最近30天北京奇迹胶原核销收入 TOP5门店",
    )
    payment = rewriter.resolve("那支付GMV呢", payment_state, session_id="delta-payment")
    assert payment.resolved_question == "最近30天北京奇迹胶原支付GMV TOP5门店"
    assert payment.delta is not None
    assert "domain_switch_to_payment" in payment.delta.operations

    payment_income = rewriter.resolve("换成支付收入呢", overall_state, session_id="delta-overall")
    assert payment_income.resolved_question == "最近30天各门店支付GMV TOP10"
    assert payment_income.delta is not None
    assert "domain_switch_to_payment" in payment_income.delta.operations

    weekly_payment = rewriter.resolve(
        "本周支付收入呢",
        ConversationState(
            session_id="delta-payment-week",
            turn_id=1,
            last_resolved_question="最近30天整体核销收入是多少？",
        ),
        session_id="delta-payment-week",
    )
    assert weekly_payment.resolved_question == "本周整体支付GMV是多少？"
    assert weekly_payment.delta is not None
    assert weekly_payment.delta.set_time_range == "本周"


def test_answer_composer_saves_latest_state_and_resolves_follow_up():
    session_id = "memory-composer-case"
    get_default_memory_store().clear(session_id)

    composer = AnswerComposer()
    first = composer.compose(
        "最近30天北京奇迹胶原核销收入 TOP5门店",
        session_id=session_id,
    )
    second = composer.compose("那上海呢", session_id=session_id)

    assert first.memory_used is False
    assert first.resolved_question == "最近30天北京奇迹胶原核销收入 TOP5门店"
    assert second.memory_used is True
    assert second.resolved_question == "最近30天上海奇迹胶原核销收入 TOP5门店"
    assert "city_name LIKE '%上海%'" in second.sql
    assert "standard_name REGEXP '奇迹胶原'" in second.sql
    assert "LIMIT 5" in second.sql
    assert second.memory_resolution["is_follow_up"] is True
    assert second.query_plan.original_question == second.resolved_question

    state = get_default_memory_store().get(session_id)
    assert state is not None
    assert state.last_question == "那上海呢"
    assert state.last_resolved_question == second.resolved_question
    assert state.template_id == second.query_plan.template_id
    assert state.last_sql == second.sql


def test_answer_composer_follow_up_top_n_updates_sql_limit():
    session_id = "memory-topn-case"
    get_default_memory_store().clear(session_id)

    composer = AnswerComposer()
    composer.compose(
        "最近30天北京奇迹胶原核销收入 TOP5门店",
        session_id=session_id,
    )
    answer = composer.compose("top3", session_id=session_id)

    assert answer.memory_used is True
    assert answer.resolved_question == "最近30天北京奇迹胶原核销收入 TOP3门店"
    assert "LIMIT 3" in answer.sql


def test_answer_composer_follow_up_channel_and_time_update_sql():
    session_id = "memory-channel-time-case"
    get_default_memory_store().clear(session_id)

    composer = AnswerComposer()
    composer.compose(
        "最近30天北京奇迹胶原核销收入 TOP5门店",
        session_id=session_id,
    )
    channel_answer = composer.compose("那私域呢", session_id=session_id)

    assert channel_answer.memory_used is True
    assert channel_answer.resolved_question.endswith("，私域")
    assert "cx_first_channel = '私域'" in channel_answer.sql

    month_answer = composer.compose("本月", session_id=session_id)

    assert month_answer.memory_used is True
    assert month_answer.resolved_question.startswith("本月")
    assert "DATETRUNC(CURRENT_DATE(), 'MONTH')" in month_answer.sql


def test_answer_composer_follow_up_payment_income_alias_and_week_time_switch():
    session_id = "memory-payment-income-alias"
    get_default_memory_store().clear(session_id)

    composer = AnswerComposer()
    composer.compose("最近30天各门店核销收入 TOP10", session_id=session_id)
    composer.compose("不要门店了，看整体", session_id=session_id)
    payment_answer = composer.compose("换成支付收入呢", session_id=session_id)

    assert payment_answer.memory_used is True
    assert payment_answer.resolved_question == "最近30天整体支付GMV是多少？"
    assert payment_answer.query_plan.template_id == "payment_gmv_summary_30d"
    assert "pay_gmv" in payment_answer.sql
    assert "pay_date" in payment_answer.sql
    assert "is_paydate_cash = 0" in payment_answer.sql
    assert "is_pay_new = 1" not in payment_answer.sql
    assert "executed_date" not in payment_answer.sql

    week_answer = composer.compose("本周支付收入呢", session_id=session_id)

    assert week_answer.resolved_question == "本周整体支付GMV是多少？"
    assert week_answer.query_plan.template_id == "payment_gmv_summary_30d"
    assert "pay_date >=" in week_answer.sql
    assert "DATE_SUB(CURRENT_DATE(),30)" not in week_answer.sql

    store_answer = composer.compose("想看北京保利店", session_id=session_id)

    assert store_answer.resolved_question == "本周整体支付GMV，北京保利店是多少？"
    assert store_answer.query_plan.template_id == "payment_gmv_summary_30d"
    assert "city_name LIKE '%北京%'" in store_answer.sql
    assert "sy_hospital_name LIKE '%保利%'" in store_answer.sql
    assert "GROUP BY" not in store_answer.sql


def test_three_turn_memory_defaults_to_latest_turn_for_template_sql():
    session_id = "memory-three-turn-latest"
    get_default_memory_store().clear(session_id)

    composer = AnswerComposer()
    first = composer.compose(
        "最近30天北京奇迹胶原核销收入 TOP5门店",
        session_id=session_id,
    )
    second = composer.compose("那上海呢", session_id=session_id)
    third = composer.compose("那奇迹童颜呢", session_id=session_id)

    assert first.memory_used is False
    assert second.resolved_question == "最近30天上海奇迹胶原核销收入 TOP5门店"
    assert third.memory_used is True
    assert third.resolved_question == "最近30天上海奇迹童颜核销收入 TOP5门店"
    assert third.memory_resolution["memory_window_size"] == 2
    assert third.memory_resolution["selected_turn_id"] == 2
    assert "city_name LIKE '%上海%'" in third.sql
    assert "standard_name REGEXP '奇迹童颜'" in third.sql
    assert "LIMIT 5" in third.sql


def test_three_turn_memory_can_reference_first_turn_explicitly():
    session_id = "memory-three-turn-first"
    get_default_memory_store().clear(session_id)

    composer = AnswerComposer()
    composer.compose(
        "最近30天北京奇迹胶原核销收入 TOP5门店",
        session_id=session_id,
    )
    composer.compose("那上海呢", session_id=session_id)
    answer = composer.compose("北京那个，换成奇迹童颜", session_id=session_id)

    assert answer.memory_used is True
    assert answer.resolved_question == "最近30天北京奇迹童颜核销收入 TOP5门店"
    assert answer.memory_resolution["selected_turn_id"] == 1
    assert "city_name LIKE '%北京%'" in answer.sql
    assert "standard_name REGEXP '奇迹童颜'" in answer.sql
    assert "LIMIT 5" in answer.sql


def test_memory_store_keeps_sliding_window_of_three_turns():
    session_id = "memory-window-size"
    get_default_memory_store().clear(session_id)

    composer = AnswerComposer()
    composer.compose("最近30天北京奇迹胶原核销收入 TOP5门店", session_id=session_id)
    composer.compose("那上海呢", session_id=session_id)
    composer.compose("top3", session_id=session_id)
    composer.compose("本月", session_id=session_id)

    window = get_default_memory_store().get_window(session_id)
    assert len(window) == 3
    assert [state.turn_id for state in window] == [2, 3, 4]
    assert window[-1].last_resolved_question.startswith("本月")
