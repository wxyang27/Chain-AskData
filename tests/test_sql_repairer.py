from app.sql.repairer import StaticSqlRepairer
from app.models.query import SemanticContract
from app.schema_graph.graph import SchemaGraph


def _graph(query: str) -> SchemaGraph:
    return SchemaGraph(
        query=query,
        tables=[
            {"table_name": "dm_opt_qy_user_execution_record_all_d"},
            {"table_name": "dm_opt_qy_order_info_all_d"},
            {"table_name": "dim_qy_tenant_info_all_d"},
        ],
        fields=[
            {"table_name": "dm_opt_qy_user_execution_record_all_d", "field_name": "dp"},
            {"table_name": "dm_opt_qy_user_execution_record_all_d", "field_name": "is_valid"},
            {"table_name": "dm_opt_qy_user_execution_record_all_d", "field_name": "executed_date"},
            {"table_name": "dm_opt_qy_user_execution_record_all_d", "field_name": "exe_income"},
            {"table_name": "dm_opt_qy_user_execution_record_all_d", "field_name": "main_order_id"},
            {"table_name": "dm_opt_qy_user_execution_record_all_d", "field_name": "revenue_category"},
            {"table_name": "dm_opt_qy_order_info_all_d", "field_name": "dp"},
            {"table_name": "dm_opt_qy_order_info_all_d", "field_name": "pay_date"},
            {"table_name": "dm_opt_qy_order_info_all_d", "field_name": "pay_gmv"},
            {"table_name": "dm_opt_qy_order_info_all_d", "field_name": "left_gmv"},
            {"table_name": "dm_opt_qy_order_info_all_d", "field_name": "left_num"},
            {"table_name": "dm_opt_qy_order_info_all_d", "field_name": "is_paydate_cash"},
            {"table_name": "dm_opt_qy_user_execution_record_all_d", "field_name": "tenant_id"},
            {"table_name": "dm_opt_qy_user_execution_record_all_d", "field_name": "standard_name"},
            {"table_name": "dim_qy_tenant_info_all_d", "field_name": "tenant_id"},
            {"table_name": "dim_qy_tenant_info_all_d", "field_name": "dp"},
            {"table_name": "dim_qy_tenant_info_all_d", "field_name": "city_name"},
            {"table_name": "dim_qy_tenant_info_all_d", "field_name": "sy_hospital_name"},
        ],
    )


def test_repairer_adds_left_num_filter_for_unverified_sql():
    sql = """SELECT SUM(t1.left_gmv) AS unverified_amount
FROM soyoung_dw.dm_opt_qy_order_info_all_d t1
WHERE t1.dp = DATE_SUB(CURRENT_DATE(), 1)"""
    contract = SemanticContract(
        metrics=["unverified_amount"],
        filters=["left_num > 0"],
    )

    result = StaticSqlRepairer().repair(
        sql=sql,
        semantic_contract=contract,
        schema_graph=_graph("昨天待核销金额是多少？"),
        errors=["business_semantics:missing_left_num_filter"],
    )

    assert result.repaired is True
    assert "t1.left_num > 0" in result.sql


def test_repairer_adds_revenue_category_filter():
    sql = """SELECT revenue_category, SUM(exe_income)
FROM soyoung_dw.dm_opt_qy_user_execution_record_all_d
WHERE dp = DATE_SUB(CURRENT_DATE(), 1)
AND is_valid = 1
GROUP BY revenue_category"""
    contract = SemanticContract(
        metrics=["execution_income"],
        filters=["revenue_category IN ('大单品','常规品','大师团')"],
    )

    result = StaticSqlRepairer().repair(
        sql=sql,
        semantic_contract=contract,
        schema_graph=_graph("最近30天大单品、常规品、大师团核销收入对比"),
        errors=["business_semantics:missing_revenue_category_filter"],
    )

    assert result.repaired is True
    assert "revenue_category IN ('大单品','常规品','大师团')" in result.sql


def test_repairer_rewrites_dual_payment_execution_metrics():
    contract = SemanticContract(
        metrics=["execution_income", "payment_gmv"],
        time_range="yesterday",
    )

    result = StaticSqlRepairer().repair(
        sql="SELECT SUM(pay_gmv) FROM soyoung_dw.dm_opt_qy_order_info_all_d",
        semantic_contract=contract,
        schema_graph=_graph("昨天核销收入和支付GMV分别是多少？"),
        errors=["business_semantics:missing_pay_date_filter"],
    )

    assert result.repaired is True
    assert "SUM(exe_income)" in result.sql
    assert "SUM(pay_gmv)" in result.sql
    assert "e.executed_date = DATE_SUB(CURRENT_DATE(),1)" in result.sql
    assert "p.pay_date = DATE_SUB(CURRENT_DATE(),1)" in result.sql


def test_repairer_rewrites_missing_revenue_category_share_dimension():
    contract = SemanticContract(
        metrics=["execution_income"],
        dimensions=["revenue_category"],
        time_range="last_30d",
    )

    result = StaticSqlRepairer().repair(
        sql="""SELECT SUM(exe_income) AS total_exe_income
FROM soyoung_dw.dm_opt_qy_user_execution_record_all_d
WHERE dp = DATE_SUB(CURRENT_DATE(), 1)
AND is_valid = 1
AND executed_date >= DATE_SUB(CURRENT_DATE(), 30)
AND executed_date <= DATE_SUB(CURRENT_DATE(), 1)""",
        semantic_contract=contract,
        schema_graph=_graph("最近30天全连锁各品类的核销收入占比"),
        errors=["missing_dimension:品类:revenue_category"],
    )

    assert result.repaired is True
    assert "revenue_category" in result.sql
    assert "SUM(SUM(exe_income)) OVER ()" in result.sql
    assert "核销收入占比" in result.sql


def test_repairer_rewrites_payment_template_to_this_week():
    contract = SemanticContract(
        metrics=["payment_gmv", "payment_user_count", "payment_aov_by_user_day"],
        filters=["is_paydate_cash = 0", "is_pay_new = 1"],
        time_range="this_week",
    )

    result = StaticSqlRepairer().repair(
        sql="""SELECT SUM(pay_gmv)
FROM soyoung_dw.dm_opt_qy_order_info_all_d
WHERE dp = DATE_SUB(CURRENT_DATE(),1)
AND is_paydate_cash = 0
AND is_pay_new = 1
AND pay_date BETWEEN DATE_SUB(CURRENT_DATE(),30) AND DATE_SUB(CURRENT_DATE(),1)""",
        semantic_contract=contract,
        schema_graph=_graph("本周新客支付人数和支付客单价"),
        errors=[],
    )

    assert result.repaired is True
    assert "WEEKDAY(CAST(CURRENT_DATE() AS DATETIME))" in result.sql
    assert "DATE_SUB(CURRENT_DATE(),30)" not in result.sql


def test_repairer_rewrites_zero_income_ratio_to_distinct_order_count():
    contract = SemanticContract(metrics=["zero_income_order_count"])

    result = StaticSqlRepairer().repair(
        sql="""SELECT CAST(SUM(CASE WHEN t1.exe_income = 0 THEN 1 ELSE 0 END) AS DOUBLE)
  / NULLIF(COUNT(*), 0) AS zero_ratio
FROM soyoung_dw.dm_opt_qy_user_execution_record_all_d t1
WHERE t1.dp = DATE_SUB(CURRENT_DATE(),1)
AND t1.is_valid = 1""",
        semantic_contract=contract,
        schema_graph=_graph("昨天哪些门店出现了超过20%的0元核销？"),
        errors=["business_semantics:zero_income_orders_must_count_main_order_id"],
    )

    assert result.repaired is True
    assert "COUNT(DISTINCT CASE WHEN t1.exe_income = 0 THEN t1.main_order_id END)" in result.sql
    assert "COUNT(DISTINCT main_order_id)" in result.sql
    assert "COUNT(*)" not in result.sql


def test_repairer_rewrites_new_customer_visit_ratio():
    contract = SemanticContract(
        metrics=["execution_income", "execution_visit_count"],
        filters=["is_valid = 1", "is_new = 1", "revenue_category = '大师团'"],
        time_range="last_7d",
    )

    result = StaticSqlRepairer().repair(
        sql="""SELECT SUM(exe_income), COUNT(DISTINCT CASE WHEN is_new = 1 THEN verify_date_id END)
FROM soyoung_dw.dm_opt_qy_user_execution_record_all_d
WHERE dp = DATE_SUB(CURRENT_DATE(), 1)
AND is_valid = 1""",
        semantic_contract=contract,
        schema_graph=_graph("最近7天大师团核销收入和新客核销人次占比"),
        errors=["business_semantics:missing_visit_ratio_nullif"],
    )

    assert result.repaired is True
    assert "COUNT(DISTINCT verify_date_id) AS 总核销人次" in result.sql
    assert "新客核销人次占比" in result.sql
    assert "revenue_category = '大师团'" in result.sql
    assert "DATE_SUB(CURRENT_DATE(),7)" in result.sql


def test_repairer_rewrites_named_city_and_item_exact_filters_to_regexp():
    result = StaticSqlRepairer().repair(
        sql="""SELECT b.sy_hospital_name, SUM(a.exe_income) AS execution_income
FROM soyoung_dw.dm_opt_qy_user_execution_record_all_d a
JOIN soyoung_dw.dim_qy_tenant_info_all_d b
ON a.tenant_id = b.tenant_id
WHERE a.dp = DATE_SUB(CURRENT_DATE(), 1)
AND b.dp = DATE_SUB(CURRENT_DATE(), 1)
AND a.is_valid = 1
AND a.executed_date >= DATE_SUB(CURRENT_DATE(), 30)
AND a.executed_date <= DATE_SUB(CURRENT_DATE(), 1)
AND a.standard_name = '奇迹胶原'
AND b.city_name = '杭州'
GROUP BY b.sy_hospital_name
ORDER BY execution_income DESC
LIMIT 5""",
        semantic_contract=SemanticContract(metrics=["execution_income"]),
        schema_graph=_graph("最近30天杭州奇迹胶原核销收入 TOP5门店"),
        errors=[
            "city_filter_should_use_regexp_or_like:city_name",
            "item_filter_should_use_regexp_or_like:standard_name",
        ],
    )

    assert result.repaired is True
    assert "b.city_name REGEXP '杭州'" in result.sql
    assert "a.standard_name REGEXP '奇迹胶原'" in result.sql
