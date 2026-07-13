from app.llm.sql_repairer import StaticSqlRepairer
from app.models.query import SemanticContract
from app.schema_graph.graph import SchemaGraph


def _graph(query: str) -> SchemaGraph:
    return SchemaGraph(
        query=query,
        tables=[
            {"table_name": "dm_opt_qy_user_execution_record_all_d"},
            {"table_name": "dm_opt_qy_order_info_all_d"},
        ],
        fields=[
            {"table_name": "dm_opt_qy_user_execution_record_all_d", "field_name": "dp"},
            {"table_name": "dm_opt_qy_user_execution_record_all_d", "field_name": "is_valid"},
            {"table_name": "dm_opt_qy_user_execution_record_all_d", "field_name": "executed_date"},
            {"table_name": "dm_opt_qy_user_execution_record_all_d", "field_name": "exe_income"},
            {"table_name": "dm_opt_qy_user_execution_record_all_d", "field_name": "revenue_category"},
            {"table_name": "dm_opt_qy_order_info_all_d", "field_name": "dp"},
            {"table_name": "dm_opt_qy_order_info_all_d", "field_name": "pay_date"},
            {"table_name": "dm_opt_qy_order_info_all_d", "field_name": "pay_gmv"},
            {"table_name": "dm_opt_qy_order_info_all_d", "field_name": "left_gmv"},
            {"table_name": "dm_opt_qy_order_info_all_d", "field_name": "left_num"},
            {"table_name": "dm_opt_qy_order_info_all_d", "field_name": "is_paydate_cash"},
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
