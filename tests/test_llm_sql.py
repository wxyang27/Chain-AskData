"""Unit tests for LLM SQL generator and safety gate."""

from dataclasses import replace

import pytest

from app.sql_generation.llm_generator import LLMSqlGenerator, LLMSqlResult
from app.sql.safety_gate import SqlSafetyGate, SqlSafetyResult
from app.models.query import QueryPlanCoT
from app.schema_graph.graph import SchemaGraph


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

def _execution_schema_graph():
    return SchemaGraph(
        query="最近30天核销收入",
        tables=[
            {
                "table_name": "dm_opt_qy_user_execution_record_all_d",
                "full_name": "soyoung_dw.dm_opt_qy_user_execution_record_all_d",
                "table_summary": "核销业务执行记录全量日表",
            },
            {
                "table_name": "dim_qy_tenant_info_all_d",
                "full_name": "soyoung_dw.dim_qy_tenant_info_all_d",
                "table_summary": "门店维度表",
            },
        ],
        fields=[
            {"table_name": "dm_opt_qy_user_execution_record_all_d",
             "field_name": "exe_income"},
            {"table_name": "dm_opt_qy_user_execution_record_all_d",
             "field_name": "tenant_id"},
            {"table_name": "dm_opt_qy_user_execution_record_all_d",
             "field_name": "dp"},
            {"table_name": "dm_opt_qy_user_execution_record_all_d",
             "field_name": "is_valid"},
            {"table_name": "dm_opt_qy_user_execution_record_all_d",
             "field_name": "executed_date"},
            {"table_name": "dm_opt_qy_user_execution_record_all_d",
             "field_name": "standard_name"},
            {"table_name": "dim_qy_tenant_info_all_d",
             "field_name": "sy_hospital_name"},
            {"table_name": "dim_qy_tenant_info_all_d",
             "field_name": "tenant_id"},
            {"table_name": "dim_qy_tenant_info_all_d",
             "field_name": "dp"},
            {"table_name": "dim_qy_tenant_info_all_d",
             "field_name": "city_name"},
        ],
        relations=[{
            "source_table": "dm_opt_qy_user_execution_record_all_d",
            "source_field": "tenant_id",
            "target_table": "dim_qy_tenant_info_all_d",
            "target_field": "tenant_id",
        }],
    )


def _cot_steps():
    return [
        QueryPlanCoT(
            step=1,
            database="soyoung_dw",
            processing_objects=[
                "dm_opt_qy_user_execution_record_all_d.exe_income",
                "dim_qy_tenant_info_all_d.sy_hospital_name",
                "dm_opt_qy_user_execution_record_all_d.tenant_id <-> dim_qy_tenant_info_all_d.tenant_id",
            ],
            operation_instructions=[
                "先筛选 dp = DATE_SUB(CURRENT_DATE(),1) AND is_valid = 1",
                "再关联 tenant_id 获取门店名称",
                "然后按门店聚合 SUM(exe_income)",
                "最后排序 DESC LIMIT 10",
            ],
            output_target="门店、核销收入",
        )
    ]


# ---------------------------------------------------------------------------
# SqlSafetyGate tests
# ---------------------------------------------------------------------------

VALID_SQL_MULTI_TABLE = """SELECT b.sy_hospital_name AS 门店,
       SUM(a.exe_income) AS 核销收入
FROM   soyoung_dw.dm_opt_qy_user_execution_record_all_d a
LEFT JOIN soyoung_dw.dim_qy_tenant_info_all_d b
ON     a.tenant_id = b.tenant_id
AND    b.dp = DATE_SUB(CURRENT_DATE(),1)
WHERE  a.dp = DATE_SUB(CURRENT_DATE(),1)
AND    a.is_valid = 1
AND    a.executed_date BETWEEN DATE_SUB(CURRENT_DATE(),30) AND DATE_SUB(CURRENT_DATE(),1)
GROUP BY b.sy_hospital_name
ORDER BY 核销收入 DESC
LIMIT 10"""

VALID_SQL_SINGLE_TABLE = """SELECT SUM(exe_income) AS 核销收入
FROM   soyoung_dw.dm_opt_qy_user_execution_record_all_d
WHERE  dp = DATE_SUB(CURRENT_DATE(),1)
AND    is_valid = 1
AND    executed_date = DATE_SUB(CURRENT_DATE(),1)"""


class TestSqlSafetyGate:
    def setup_method(self):
        self.gate = SqlSafetyGate()
        self.sg = _execution_schema_graph()

    def test_accepts_valid_multi_table_sql(self):
        result = self.gate.validate(VALID_SQL_MULTI_TABLE, self.sg)
        assert result.passed is True
        assert result.errors == []

    def test_accepts_valid_single_table_sql(self):
        result = self.gate.validate(VALID_SQL_SINGLE_TABLE, self.sg)
        assert result.passed is True

    def test_rejects_insert_statement(self):
        result = self.gate.validate(
            "INSERT INTO t VALUES (1)", self.sg,
        )
        assert "forbidden_statement" in result.errors[0]

    def test_rejects_unknown_table(self):
        result = self.gate.validate(
            "SELECT * FROM soyoung_dw.invented_table WHERE dp = 'x'",
            self.sg,
        )
        assert any("unknown_table" in e for e in result.errors)

    def test_rejects_unknown_field(self):
        result = self.gate.validate(
            "SELECT a.invented_field FROM soyoung_dw.dm_opt_qy_user_execution_record_all_d a WHERE a.dp = 'x' AND a.is_valid = 1 AND a.executed_date = 'x'",
            self.sg,
        )
        assert any("unknown_field" in e for e in result.errors)

    def test_rejects_missing_dp_filter_multi_table(self):
        sql = """SELECT b.sy_hospital_name
FROM   soyoung_dw.dm_opt_qy_user_execution_record_all_d a
LEFT JOIN soyoung_dw.dim_qy_tenant_info_all_d b
ON     a.tenant_id = b.tenant_id
WHERE  a.is_valid = 1
AND    a.executed_date = DATE_SUB(CURRENT_DATE(),1)
LIMIT 10"""
        result = self.gate.validate(sql, self.sg)
        assert any("missing_dp_filter" in e for e in result.errors)

    def test_rejects_missing_dp_filter_single_table(self):
        sql = "SELECT SUM(exe_income) FROM soyoung_dw.dm_opt_qy_user_execution_record_all_d WHERE is_valid = 1 AND executed_date = 'x'"
        result = self.gate.validate(sql, self.sg)
        assert any("missing_dp_filter" in e for e in result.errors)

    def test_rejects_dp_range_on_snapshot_table(self):
        sql = """SELECT SUM(t1.exe_income) AS exe_income
FROM soyoung_dw.dm_opt_qy_user_execution_record_all_d t1
WHERE t1.cx_first_channel = '私域'
AND t1.is_valid = 1
AND t1.executed_date >= DATE_SUB(CURRENT_DATE(), 29)
AND t1.executed_date <= CURRENT_DATE()
AND t1.dp >= DATE_SUB(CURRENT_DATE(), 29)
AND t1.dp <= CURRENT_DATE()"""

        result = self.gate.validate(sql, self.sg)

        assert result.passed is False
        assert any("dp_must_equal_yesterday_not_range" in e for e in result.errors)

    def test_rejects_dp_range_on_item_query_snapshot_table(self):
        sql = """SELECT standard_name AS 品项, SUM(exe_income) AS 核销收入
FROM soyoung_dw.dm_opt_qy_user_execution_record_all_d
WHERE standard_name = '奇迹胶原'
AND is_valid = 1
AND executed_date >= DATE_SUB(CURRENT_DATE(), 30)
AND executed_date <= DATE_SUB(CURRENT_DATE(), 1)
AND dp >= DATE_SUB(CURRENT_DATE(), 30)
AND dp <= DATE_SUB(CURRENT_DATE(), 1)
GROUP BY standard_name"""

        result = self.gate.validate(sql, self.sg)

        assert result.passed is False
        assert any("dp_must_equal_yesterday_not_range" in e for e in result.errors)

    def test_rejects_dp_equal_non_yesterday_on_snapshot_table(self):
        sql = """SELECT SUM(t1.exe_income) AS exe_income
FROM soyoung_dw.dm_opt_qy_user_execution_record_all_d t1
WHERE t1.dp = CURRENT_DATE()
AND t1.is_valid = 1
AND t1.executed_date = DATE_SUB(CURRENT_DATE(), 1)"""

        result = self.gate.validate(sql, self.sg)

        assert result.passed is False
        assert any("dp_must_equal_DATE_SUB_CURRENT_DATE_1" in e for e in result.errors)

    def test_rejects_named_city_query_without_city_filter(self):
        city_graph = replace(self.sg, query="本月北京地区奇迹胶原品项的核销收入")
        sql = """SELECT standard_name AS 品项, SUM(exe_income) AS 核销收入
FROM soyoung_dw.dm_opt_qy_user_execution_record_all_d
WHERE standard_name = '奇迹胶原'
AND is_valid = 1
AND executed_date >= DATE_SUB(CURRENT_DATE(), 30)
AND executed_date <= DATE_SUB(CURRENT_DATE(), 1)
AND dp = DATE_SUB(CURRENT_DATE(), 1)
GROUP BY standard_name"""

        result = self.gate.validate(sql, city_graph)

        assert result.passed is False
        assert "missing_city_filter:city_name" in result.errors

    def test_accepts_named_city_query_with_city_filter(self):
        city_graph = replace(self.sg, query="北京地区奇迹胶原品项的核销收入")
        sql = """SELECT SUM(a.exe_income) AS 核销收入
FROM soyoung_dw.dm_opt_qy_user_execution_record_all_d a
LEFT JOIN soyoung_dw.dim_qy_tenant_info_all_d b
ON a.tenant_id = b.tenant_id
AND b.dp = DATE_SUB(CURRENT_DATE(), 1)
WHERE a.standard_name = '奇迹胶原'
AND b.city_name = '北京市'
AND a.is_valid = 1
AND a.executed_date >= DATE_SUB(CURRENT_DATE(), 30)
AND a.executed_date <= DATE_SUB(CURRENT_DATE(), 1)
AND a.dp = DATE_SUB(CURRENT_DATE(), 1)"""

        result = self.gate.validate(sql, city_graph)

        assert result.passed is True
        assert result.errors == []

    def test_rejects_this_month_as_last_30d(self):
        month_graph = replace(self.sg, query="本月北京地区奇迹胶原品项的核销收入")
        sql = """SELECT SUM(a.exe_income) AS 核销收入
FROM soyoung_dw.dm_opt_qy_user_execution_record_all_d a
LEFT JOIN soyoung_dw.dim_qy_tenant_info_all_d b
ON a.tenant_id = b.tenant_id
AND b.dp = DATE_SUB(CURRENT_DATE(), 1)
WHERE a.standard_name = '奇迹胶原'
AND b.city_name = '北京市'
AND a.is_valid = 1
AND a.executed_date >= DATE_SUB(CURRENT_DATE(), 30)
AND a.executed_date <= DATE_SUB(CURRENT_DATE(), 1)
AND a.dp = DATE_SUB(CURRENT_DATE(), 1)"""

        result = self.gate.validate(sql, month_graph)

        assert result.passed is False
        assert "date_semantics:this_month_must_not_be_last_30d" in result.errors

    def test_accepts_this_month_mtd_window(self):
        month_graph = replace(self.sg, query="本月北京地区奇迹胶原品项的核销收入")
        sql = """SELECT SUM(a.exe_income) AS 核销收入
FROM soyoung_dw.dm_opt_qy_user_execution_record_all_d a
LEFT JOIN soyoung_dw.dim_qy_tenant_info_all_d b
ON a.tenant_id = b.tenant_id
AND b.dp = DATE_SUB(CURRENT_DATE(), 1)
WHERE a.standard_name = '奇迹胶原'
AND b.city_name = '北京市'
AND a.is_valid = 1
AND a.executed_date >= DATETRUNC(CURRENT_DATE(), 'MONTH')
AND a.executed_date <= DATE_SUB(CURRENT_DATE(), 1)
AND a.dp = DATE_SUB(CURRENT_DATE(), 1)"""

        result = self.gate.validate(sql, month_graph)

        assert result.passed is True
        assert result.errors == []

    def test_rejects_standard_name_aliased_as_store(self):
        sql = """SELECT standard_name AS 门店, SUM(exe_income) AS 核销收入
FROM soyoung_dw.dm_opt_qy_user_execution_record_all_d
WHERE is_valid = 1
AND executed_date = DATE_SUB(CURRENT_DATE(), 1)
AND dp = DATE_SUB(CURRENT_DATE(), 1)
GROUP BY standard_name"""

        result = self.gate.validate(sql, self.sg)

        assert "alias_semantics:standard_name_is_item_not_store" in result.errors

    def test_rejects_city_breakdown_without_city_name(self):
        city_graph = replace(self.sg, query="本月各城市核销收入")
        sql = """SELECT b.sy_hospital_name AS 门店, SUM(a.exe_income) AS 核销收入
FROM soyoung_dw.dm_opt_qy_user_execution_record_all_d a
LEFT JOIN soyoung_dw.dim_qy_tenant_info_all_d b
ON a.tenant_id = b.tenant_id
AND b.dp = DATE_SUB(CURRENT_DATE(), 1)
WHERE a.is_valid = 1
AND a.executed_date >= DATETRUNC(CURRENT_DATE(), 'MONTH')
AND a.executed_date <= DATE_SUB(CURRENT_DATE(), 1)
AND a.dp = DATE_SUB(CURRENT_DATE(), 1)
GROUP BY b.sy_hospital_name"""

        result = self.gate.validate(sql, city_graph)

        assert "missing_dimension:城市:city_name" in result.errors

    def test_rejects_new_old_breakdown_without_is_new(self):
        new_old_graph = replace(self.sg, query="本月新老客核销收入")
        sql = """SELECT tenant_id, SUM(exe_income) AS 核销收入
FROM soyoung_dw.dm_opt_qy_user_execution_record_all_d
WHERE is_valid = 1
AND executed_date >= DATETRUNC(CURRENT_DATE(), 'MONTH')
AND executed_date <= DATE_SUB(CURRENT_DATE(), 1)
AND dp = DATE_SUB(CURRENT_DATE(), 1)
GROUP BY tenant_id"""

        result = self.gate.validate(sql, new_old_graph)

        assert "missing_dimension:新老客:is_new" in result.errors

    def test_rejects_missing_is_valid(self):
        sql = "SELECT exe_income FROM soyoung_dw.dm_opt_qy_user_execution_record_all_d WHERE dp = 'x' AND executed_date = 'x'"
        result = self.gate.validate(sql, self.sg)
        assert any("missing_is_valid_filter" in e for e in result.errors)

    def test_rejects_named_item_without_standard_name_filter(self):
        item_graph = replace(self.sg, query="本月北京地区奇迹胶原核销收入")
        sql = """SELECT SUM(t1.exe_income) AS execution_income
FROM soyoung_dw.dm_opt_qy_user_execution_record_all_d t1
JOIN soyoung_dw.dim_qy_tenant_info_all_d t2
ON t1.tenant_id = t2.tenant_id
WHERE t1.dp = DATE_SUB(CURRENT_DATE(), 1)
AND t2.dp = DATE_SUB(CURRENT_DATE(), 1)
AND t1.is_valid = 1
AND t1.executed_date >= DATETRUNC(CURRENT_DATE(), 'MONTH')
AND t1.executed_date <= DATE_SUB(CURRENT_DATE(), 1)
AND t2.city_name = '北京市'"""

        result = self.gate.validate(sql, item_graph)

        assert "missing_item_filter:standard_name" in result.errors

    def test_accepts_named_item_with_standard_name_filter(self):
        item_graph = replace(self.sg, query="本月北京地区奇迹胶原核销收入")
        sql = """SELECT SUM(t1.exe_income) AS execution_income
FROM soyoung_dw.dm_opt_qy_user_execution_record_all_d t1
JOIN soyoung_dw.dim_qy_tenant_info_all_d t2
ON t1.tenant_id = t2.tenant_id
WHERE t1.dp = DATE_SUB(CURRENT_DATE(), 1)
AND t2.dp = DATE_SUB(CURRENT_DATE(), 1)
AND t1.is_valid = 1
AND t1.executed_date >= DATETRUNC(CURRENT_DATE(), 'MONTH')
AND t1.executed_date <= DATE_SUB(CURRENT_DATE(), 1)
AND t2.city_name = '北京市'
AND t1.standard_name = '奇迹胶原'"""

        result = self.gate.validate(sql, item_graph)

        assert result.passed is True

    def test_rejects_order_by_without_limit(self):
        sql = """SELECT exe_income
FROM   soyoung_dw.dm_opt_qy_user_execution_record_all_d
WHERE  dp = DATE_SUB(CURRENT_DATE(),1)
AND    is_valid = 1
AND    executed_date = DATE_SUB(CURRENT_DATE(),1)
ORDER BY exe_income DESC"""
        result = self.gate.validate(sql, self.sg)
        assert any("order_by_without_limit" in e for e in result.errors)

    def test_accepts_with_cte(self):
        sql = """WITH base AS (
  SELECT exe_income, dp, is_valid, executed_date
  FROM soyoung_dw.dm_opt_qy_user_execution_record_all_d
  WHERE dp = DATE_SUB(CURRENT_DATE(),1)
  AND is_valid = 1
  AND executed_date = DATE_SUB(CURRENT_DATE(),1)
)
SELECT SUM(exe_income) FROM base"""
        result = self.gate.validate(sql, self.sg)
        assert result.passed is True

    def test_extracts_tables_correctly(self):
        tables = self.gate._extract_tables(VALID_SQL_MULTI_TABLE)
        assert "dm_opt_qy_user_execution_record_all_d" in tables
        assert "dim_qy_tenant_info_all_d" in tables

    def test_extracts_fields_skips_db_prefix(self):
        fields = self.gate._extract_fields(VALID_SQL_MULTI_TABLE)
        assert "a.exe_income" in fields or any(
            "exe_income" in f for f in fields
        )
        # "soyoung_dw" should not appear as a field prefix
        assert not any(f.startswith("soyoung_dw.") for f in fields)

    def test_rejects_date_sub_with_three_arguments(self):
        sql = """SELECT SUM(exe_income)
FROM soyoung_dw.dm_opt_qy_user_execution_record_all_d
WHERE dp = DATE_SUB(CURRENT_DATE(), 1)
AND is_valid = 1
AND executed_date >= DATE_SUB(
    TO_DATE(CURRENT_DATE(), 'yyyy-mm-dd'),
    WEEKDAY(CURRENT_DATE()) + 1,
    'dd'
)"""

        result = self.gate.validate(sql, self.sg)

        assert any("date_sub_invalid_arity" in error for error in result.errors)

    def test_rejects_executed_date_upper_bound_current_date(self):
        sql = """SELECT SUM(exe_income)
FROM soyoung_dw.dm_opt_qy_user_execution_record_all_d
WHERE dp = DATE_SUB(CURRENT_DATE(), 1)
AND is_valid = 1
AND executed_date >= DATE_SUB(CURRENT_DATE(), 30)
AND executed_date <= CURRENT_DATE()"""

        result = self.gate.validate(sql, self.sg)

        assert any(
            "executed_date_end_must_be_yesterday" in error
            for error in result.errors
        )

    def test_rejects_this_week_range_from_sunday_to_future_saturday(self):
        this_week_graph = replace(self.sg, query="本周核销收入是多少？")
        sql = """SELECT SUM(exe_income)
FROM soyoung_dw.dm_opt_qy_user_execution_record_all_d
WHERE dp = DATE_SUB(CURRENT_DATE(), 1)
AND is_valid = 1
AND executed_date >= DATE_SUB(CURRENT_DATE(), WEEKDAY(CURRENT_DATE()) + 1)
AND executed_date <= DATE_SUB(CURRENT_DATE(), WEEKDAY(CURRENT_DATE()) - 5)"""

        result = self.gate.validate(sql, this_week_graph)

        assert any("this_week_start_must_be_monday" in error for error in result.errors)
        assert any("this_week_end_must_be_yesterday" in error for error in result.errors)

    def test_accepts_this_week_range_from_monday_to_yesterday(self):
        this_week_graph = replace(self.sg, query="本周核销收入是多少？")
        sql = """SELECT SUM(exe_income)
FROM soyoung_dw.dm_opt_qy_user_execution_record_all_d
WHERE dp = DATE_SUB(CURRENT_DATE(), 1)
AND is_valid = 1
AND executed_date >= DATE_SUB(
    CURRENT_DATE(),
    WEEKDAY(CAST(CURRENT_DATE() AS DATETIME))
)
AND executed_date <= DATE_SUB(CURRENT_DATE(), 1)"""

        result = self.gate.validate(sql, this_week_graph)

        assert result.passed is True
        assert result.errors == []


# ---------------------------------------------------------------------------
# LLMSqlGenerator tests
# ---------------------------------------------------------------------------

class FakeSqlClient:
    def __init__(self, payload=None, error: Exception | None = None):
        self.payload = payload or {}
        self.error = error
        self.calls = []

    def chat_json(self, *, model, messages, temperature=0, timeout_seconds=30):
        self.calls.append({"model": model, "messages": messages})
        if self.error:
            raise self.error
        return self.payload


GOOD_SQL_PAYLOAD = {
    "sql": "SELECT SUM(exe_income) FROM soyoung_dw.dm_opt_qy_user_execution_record_all_d WHERE dp = DATE_SUB(CURRENT_DATE(),1) AND is_valid = 1 AND executed_date = DATE_SUB(CURRENT_DATE(),1)",
    "used_tables": ["soyoung_dw.dm_opt_qy_user_execution_record_all_d"],
    "used_fields": ["dm_opt_qy_user_execution_record_all_d.exe_income"],
    "explanation": "昨日核销收入汇总",
}


class TestLLMSqlGenerator:
    def test_disabled_returns_error(self):
        gen = LLMSqlGenerator(enabled=False)
        result = gen.generate(cot_steps=_cot_steps(), schema_graph=_execution_schema_graph())
        assert result.generated is False
        assert result.error == "llm_disabled"

    def test_empty_cot_returns_error(self):
        gen = LLMSqlGenerator(enabled=True)
        result = gen.generate(cot_steps=[], schema_graph=_execution_schema_graph())
        assert result.generated is False
        assert result.error == "empty_cot_steps"

    def test_missing_schema_graph_returns_error(self):
        gen = LLMSqlGenerator(enabled=True)
        result = gen.generate(cot_steps=_cot_steps(), schema_graph=None)
        assert result.generated is False
        assert result.error == "schema_graph_missing"

    def test_parses_valid_response(self):
        client = FakeSqlClient(GOOD_SQL_PAYLOAD)
        gen = LLMSqlGenerator(enabled=True, client=client)
        result = gen.generate(cot_steps=_cot_steps(), schema_graph=_execution_schema_graph())

        assert result.generated is True
        assert "SELECT" in result.sql
        assert "exe_income" in result.sql
        assert "dm_opt_qy_user_execution_record_all_d" in str(result.used_tables)
        assert "昨日核销收入汇总" in result.explanation

    def test_handles_client_exception(self):
        client = FakeSqlClient(error=RuntimeError("qwen offline"))
        gen = LLMSqlGenerator(enabled=True, client=client)
        result = gen.generate(cot_steps=_cot_steps(), schema_graph=_execution_schema_graph())

        assert result.generated is False
        assert "qwen offline" in result.error

    def test_handles_empty_sql_in_response(self):
        client = FakeSqlClient({"sql": "", "explanation": "no sql"})
        gen = LLMSqlGenerator(enabled=True, client=client)
        result = gen.generate(cot_steps=_cot_steps(), schema_graph=_execution_schema_graph())

        assert result.generated is False
        assert result.error == "empty_sql"
