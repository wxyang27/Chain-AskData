from app.feishu_bot.intent import classify_bot_intent


def test_follow_up_area_question_is_data_query_for_feishu_entry():
    result = classify_bot_intent("那华北大区呢")

    assert result.intent == "data_query"
