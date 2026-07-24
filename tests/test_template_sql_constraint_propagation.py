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
    assert "EXISTS (" not in sql
    assert "pay_date >=" in sql
    assert "GROUP BY" not in sql


def test_template_does_not_treat_topn_store_dimension_as_named_store_filter():
    plan = _minimal_plan(
        "本周北京奇迹胶原核销收入TOP3门店",
        "execution_metric_summary_30d",
        time_range="本周",
    )
    plan.semantic_contract.metrics = ["execution_income"]
    plan.semantic_contract.dimensions = ["sy_hospital_name"]
    plan.semantic_contract.time_range = "this_week"

    sql = SqlGenerator().generate(plan)

    assert "b.sy_hospital_name AS 门店" in sql
    assert "b.city_name LIKE '%北京%'" in sql
    assert "a.standard_name REGEXP '奇迹胶原'" in sql
    assert "sy_hospital_name LIKE" not in sql
    assert "LIMIT 3" in sql


def test_template_generates_payment_store_breakdown_without_top_from_semantic_contract():
    plan = _minimal_plan(
        "本月各门店支付GMV",
        "payment_metric_summary_30d",
        time_range="本月MTD（自然月1日至昨天）",
    )
    plan.semantic_contract.metrics = ["payment_gmv"]
    plan.semantic_contract.dimensions = ["sy_hospital_name"]
    plan.semantic_contract.time_range = "this_month_mtd"

    sql = SqlGenerator().generate(plan)

    assert "b.sy_hospital_name AS 门店" in sql
    assert "SUM(a.pay_gmv) AS 支付GMV" in sql
    assert "GROUP BY b.sy_hospital_name" in sql
    assert "DATETRUNC(CURRENT_DATE(), 'MONTH')" in sql
    assert "area_name LIKE" not in sql
    assert "LIMIT" not in sql


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


def test_template_generates_execution_service_point_with_named_store_filter():
    plan = _minimal_plan(
        "本周北京保利店核销服务点是多少？",
        "execution_metric_summary_30d",
        time_range="本周",
    )
    plan.semantic_contract.metrics = ["execution_service_point_count"]
    plan.semantic_contract.time_range = "this_week"

    sql = SqlGenerator().generate(plan)

    assert "SUM(a.exe_cnt) AS 核销服务点数" in sql
    assert "executed_date >=" in sql
    assert "is_valid = 1" in sql
    assert "city_name LIKE '%北京%'" in sql
    assert "sy_hospital_name LIKE '%保利%'" in sql
    assert "exe_income" not in sql


def test_template_generates_p0_order_and_unverified_metric_clusters():
    payment_plan = _minimal_plan("最近30天各门店支付订单数 TOP10", "payment_metric_summary_30d")
    payment_plan.semantic_contract.metrics = ["payment_order_count"]
    payment_plan.semantic_contract.dimensions = ["sy_hospital_name"]
    payment_sql = SqlGenerator().generate(payment_plan)

    assert "COUNT(DISTINCT a.main_order_id) AS 支付订单数" in payment_sql
    assert "b.sy_hospital_name AS 门店" in payment_sql
    assert "is_paydate_cash = 0" in payment_sql
    assert "pay_date BETWEEN" in payment_sql
    assert "LIMIT 10" in payment_sql

    unverified_plan = _minimal_plan("截至昨天各城市待核销服务点排行TOP5", "unverified_inventory_summary")
    unverified_plan.semantic_contract.metrics = ["unverified_service_point_count"]
    unverified_plan.semantic_contract.dimensions = ["city_name"]
    unverified_sql = SqlGenerator().generate(unverified_plan)

    assert "SUM(a.left_num) AS 待核销服务点数" in unverified_sql
    assert "b.city_name AS 城市" in unverified_sql
    assert "left_num > 0" in unverified_sql
    assert "pay_date" not in unverified_sql
    assert "executed_date" not in unverified_sql
    assert "LIMIT 5" in unverified_sql


def test_template_generates_p1_efficiency_metric_clusters():
    income_per_point_plan = _minimal_plan("最近30天各大区单服务点收入", "execution_metric_summary_30d")
    income_per_point_plan.semantic_contract.metrics = ["income_per_service_point"]
    income_per_point_plan.semantic_contract.dimensions = ["area_name"]
    income_per_point_sql = SqlGenerator().generate(income_per_point_plan)

    assert "SUM(a.exe_income) / NULLIF(SUM(a.exe_cnt),0) AS 单服务点收入" in income_per_point_sql
    assert "b.area_name AS 大区" in income_per_point_sql
    assert "GROUP BY b.area_name" in income_per_point_sql

    points_per_user_plan = _minimal_plan(
        "本月北京人均核销服务点是多少？",
        "execution_metric_summary_30d",
        time_range="本月MTD（自然月1日至昨天）",
    )
    points_per_user_plan.semantic_contract.metrics = ["service_points_per_user"]
    points_per_user_sql = SqlGenerator().generate(points_per_user_plan)

    assert "SUM(a.exe_cnt) / NULLIF(COUNT(DISTINCT a.customer_id),0) AS 人均核销服务点" in points_per_user_sql
    assert "DATETRUNC(CURRENT_DATE(), 'MONTH')" in points_per_user_sql
    assert "city_name LIKE '%北京%'" in points_per_user_sql
