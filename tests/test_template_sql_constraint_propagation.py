from app.models.query import QueryPlan
from app.sql_generation.template_generator import SqlGenerator


def _minimal_plan(question: str, template_id: str, time_range: str = "最近30天") -> QueryPlan:
    return QueryPlan(
        intent="nl2sql",
        business_domain="test",
        original_question=question,
        template_id=template_id,
        time_range=time_range,
        metrics=[],
    )


def test_template_preserves_new_old_dimension_when_channel_filter_is_added():
    sql = SqlGenerator().generate(
        _minimal_plan(
            "最近30天新客和老客核销收入、人次、客单价分别是多少？，私域",
            "new_old_customer_execution_30d",
        )
    )

    assert "CASE WHEN is_new = 1" in sql
    assert "cx_first_channel = '私域'" in sql
    assert "GROUP BY CASE WHEN is_new = 1" in sql


def test_template_adds_city_filter_to_single_table_zero_income_query():
    sql = SqlGenerator().generate(
        _minimal_plan(
            "本月0元单数量和核销人数是多少？，杭州",
            "zero_income_orders_30d",
            time_range="本月MTD（自然月1日至昨天）",
        )
    )

    assert "exe_income = 0" in sql
    assert "DATETRUNC(CURRENT_DATE(), 'MONTH')" in sql
    assert "tenant_id IN (" in sql
    assert "dim_qy_tenant_info_all_d" in sql
    assert "city_name LIKE '%杭州%'" in sql


def test_template_generates_overall_execution_income_without_ranking_dimension():
    sql = SqlGenerator().generate(
        _minimal_plan(
            "最近30天整体核销收入是多少？",
            "execution_income_summary_30d",
        )
    )

    assert "SUM(exe_income)" in sql
    assert "sy_hospital_name" not in sql
    assert "GROUP BY" not in sql
    assert "ORDER BY" not in sql
    assert "LIMIT" not in sql


def test_template_generates_item_income_share_with_nullif():
    sql = SqlGenerator().generate(
        _minimal_plan(
            "最近30天品项核销收入占比 TOP20",
            "standard_item_income_share_top20_30d",
        )
    )

    assert "standard_name" in sql
    assert "SUM(exe_income)" in sql
    assert "NULLIF" in sql
    assert "LIMIT 20" in sql


def test_template_generates_payment_gmv_store_topn_with_preserved_constraints():
    sql = SqlGenerator().generate(
        _minimal_plan(
            "最近30天北京奇迹胶原支付GMV TOP5门店",
            "payment_gmv_store_topn_30d",
        )
    )

    assert "pay_gmv" in sql
    assert "pay_date" in sql
    assert "is_paydate_cash = 0" in sql
    assert "city_name LIKE '%北京%'" in sql
    assert "standard_name REGEXP '奇迹胶原'" in sql
    assert "LIMIT 5" in sql
    assert "executed_date" not in sql


def test_template_generates_overall_payment_summary_with_time_override():
    plan = _minimal_plan(
        "本周整体支付收入是多少？",
        "payment_gmv_summary_30d",
        time_range="本周",
    )
    plan.semantic_contract.time_range = "this_week"
    sql = SqlGenerator().generate(plan)

    assert "SUM(pay_gmv)" in sql
    assert "pay_date >=" in sql
    assert "is_paydate_cash = 0" in sql
    assert "is_pay_new = 1" not in sql
    assert "executed_date" not in sql
    assert "GROUP BY" not in sql


def test_template_adds_named_store_filter_to_overall_payment_summary():
    plan = _minimal_plan(
        "本周整体支付GMV是多少？，北京保利店",
        "payment_gmv_summary_30d",
        time_range="本周",
    )
    plan.semantic_contract.time_range = "this_week"

    sql = SqlGenerator().generate(plan)

    assert "pay_gmv" in sql
    assert "city_name LIKE '%北京%'" in sql
    assert "sy_hospital_name LIKE '%保利%'" in sql
    assert "tenant_id IN (" in sql
    assert "GROUP BY" not in sql


def test_template_adds_named_area_filter_to_overall_payment_summary():
    plan = _minimal_plan(
        "本周华北大区支付GMV是多少？",
        "payment_gmv_summary_30d",
        time_range="本周",
    )
    plan.semantic_contract.time_range = "this_week"

    sql = SqlGenerator().generate(plan)

    assert "SUM(pay_gmv)" in sql
    assert "area_name LIKE '%华北%'" in sql
    assert "tenant_id IN (" in sql
    assert "pay_date >=" in sql
    assert "GROUP BY" not in sql


def test_template_generates_area_execution_and_payment_breakdowns():
    execution_sql = SqlGenerator().generate(
        _minimal_plan("最近30天各大区核销收入", "area_execution_30d")
    )
    payment_sql = SqlGenerator().generate(
        _minimal_plan("最近30天各大区支付GMV", "area_payment_30d")
    )

    assert "b.area_name AS 大区" in execution_sql
    assert "SUM(a.exe_income)" in execution_sql
    assert "GROUP BY b.area_name" in execution_sql

    assert "b.area_name AS 大区" in payment_sql
    assert "SUM(a.pay_gmv)" in payment_sql
    assert "is_paydate_cash = 0" in payment_sql
    assert "GROUP BY b.area_name" in payment_sql
