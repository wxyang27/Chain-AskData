from decimal import Decimal

from app.feishu_bot.cards import build_processing_card, build_query_card, build_unsupported_card
from app.models.query import QueryPlan, QueryResponse, ValidationResult


def test_query_card_uses_horizontal_bar_chart_for_numeric_ranking():
    response = QueryResponse(
        project="chain",
        question_summary="最近30天北京奇迹胶原核销收入TOP3门店",
        query_plan=QueryPlan(
            intent="ranking",
            business_domain="chain",
            original_question="最近30天北京奇迹胶原核销收入TOP3门店",
            metrics=[],
        ),
        sql="SELECT 1",
        validation=ValidationResult(passed=True),
        caliber_notes=[],
        sql_source="llm",
        execution_enabled=True,
        execution_mode="maxcompute",
        execution_status="success",
        sample_rows=[
            {
                "sy_hospital_name": "新氧青春诊所(北京保利总部店) No.001",
                "total_income": Decimal("276989.5082"),
            },
            {
                "sy_hospital_name": "新氧青春诊所(北京合生汇店) No.009",
                "total_income": Decimal("241977.6501"),
            },
            {
                "sy_hospital_name": "新氧青春诊所(北京蓝色港湾店) No.023",
                "total_income": Decimal("186332.3672"),
            },
        ],
        row_count=3,
    )

    card = build_query_card(response)
    elements = card["body"]["elements"]
    chart = next(element for element in elements if element["tag"] == "chart")

    assert card["schema"] == "2.0"
    assert chart["chart_spec"]["type"] == "bar"
    assert chart["chart_spec"]["direction"] == "horizontal"
    assert chart["chart_spec"]["xField"] == "value"
    assert chart["chart_spec"]["yField"] == "name"
    assert chart["chart_spec"]["data"]["values"][0]["value"] == 276989.5082
    assert chart["chart_spec"]["data"]["values"][0]["name"] == "1. No.001"
    assert chart["chart_spec"]["bar"]["style"]["fill"] == "#2E9E6F"


def test_query_card_formats_sql_block_for_readability():
    response = QueryResponse(
        project="chain",
        question_summary="核销收入TOP门店",
        query_plan=QueryPlan(
            intent="ranking",
            business_domain="chain",
            original_question="核销收入TOP门店",
            metrics=[],
        ),
        sql=(
            "SELECT b.sy_hospital_name, SUM(a.exe_income) AS total_income "
            "FROM soyoung_dw.dm_opt_qy_user_execution_record_all_d a "
            "LEFT JOIN soyoung_dw.dim_qy_tenant_info_all_d b ON a.tenant_id = b.tenant_id "
            "WHERE a.is_valid = 1 AND a.executed_date >= '2026-07-01' "
            "GROUP BY b.sy_hospital_name ORDER BY total_income DESC LIMIT 5"
        ),
        validation=ValidationResult(passed=True),
        caliber_notes=[],
        sql_source="llm",
        execution_enabled=True,
        execution_mode="maxcompute",
        execution_status="success",
        sample_rows=[],
        row_count=0,
    )

    card = build_query_card(response)
    sql_panel = next(element for element in card["body"]["elements"] if element["tag"] == "collapsible_panel")
    sql_markdown = sql_panel["elements"][0]["content"]

    assert "\nFROM soyoung_dw" in sql_markdown
    assert "\nLEFT JOIN soyoung_dw" in sql_markdown
    assert "\nWHERE a.is_valid" in sql_markdown
    assert "\n  AND a.executed_date" in sql_markdown
    assert "\nGROUP BY b.sy_hospital_name" in sql_markdown


def test_unsupported_card_uses_simple_markdown_without_stacked_color_blocks():
    card = build_unsupported_card("下午好")
    elements = card["body"]["elements"]

    assert card["header"]["template"] == "default"
    assert all(element["tag"] == "markdown" for element in elements)
    assert "收到你的问题" in elements[0]["content"]
    assert "本月华东大区支付GMV" in elements[1]["content"]


def test_processing_card_is_minimal_and_shows_resolved_question():
    card = build_processing_card("那top3呢", "本周北京奇迹胶原核销收入TOP3门店")
    content = card["body"]["elements"][0]["content"]

    assert card["header"]["template"] == "default"
    assert card["header"]["title"]["content"] == " "
    assert "subtitle" not in card["header"]
    assert card["header"]["text_tag_list"][0]["text"]["content"] == "处理中"
    assert "CatData" not in content
    assert "新氧连锁经营数据问数助手" not in content
    assert "收到你的问题啦：那top3呢" in content
    assert "补齐问题：本周北京奇迹胶原核销收入TOP3门店" in content
    assert "我先按经营口径看一下，稍后把结果回复在这里~" in content
