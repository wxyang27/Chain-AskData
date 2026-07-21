from decimal import Decimal

from app.feishu_bot.cards import build_query_card
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
