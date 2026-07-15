from app.execution.objects import SqlExecutionResult
from app.execution.base import SqlExecutor
from app.feedback.repair_policy import RepairPolicy
from app.feedback.result_validator import ResultValidator
from app.models.query import DimensionPlan, MetricPlan, QueryPlan
from app.askdata_pipeline.pipeline import AskDataPipeline


def _plan(question: str = "最近30天各门店核销收入 TOP10") -> QueryPlan:
    return QueryPlan(
        intent="nl2sql",
        business_domain="连锁经管",
        original_question=question,
        template_id="store_income_top10_30d",
        metrics=[
            MetricPlan(
                canonical="execution_income",
                display_name="核销收入",
                formula="SUM(exe_income)",
            )
        ],
    )


def test_result_validator_detects_execution_failed_unknown_field():
    execution = SqlExecutionResult(
        enabled=True,
        mode="sqlite",
        status="failed",
        error="sqlite_execution_failed: no such column: bad_field",
        dry_run=False,
    )

    validation = ResultValidator().validate(
        sql="SELECT bad_field FROM demo",
        query_plan=_plan(),
        execution_result=execution,
    )
    advice = RepairPolicy().advise(
        execution_result=execution,
        result_validation=validation,
        safety_errors=[],
        sql_source="llm",
    )

    assert validation.passed is False
    assert "execution_failed" in validation.errors[0]
    assert "unknown_field" in advice.categories
    assert "run_static_repair_against_schema_graph" in advice.suggested_actions


def test_repair_policy_classifies_date_function_error():
    execution = SqlExecutionResult(
        enabled=True,
        mode="mock",
        status="failed",
        error="DATE_TRUNC is not supported",
    )
    validation = ResultValidator().validate(
        sql="SELECT DATE_TRUNC('month', CURRENT_DATE())",
        query_plan=_plan(),
        execution_result=execution,
    )

    advice = RepairPolicy().advise(
        execution_result=execution,
        result_validation=validation,
        safety_errors=["mc_syntax:DATE_TRUNC is not supported in MaxCompute"],
        sql_source="llm",
    )

    assert "date_function_error" in advice.categories
    assert "rewrite_non_maxcompute_date_functions" in advice.suggested_actions


def test_result_validator_detects_empty_result():
    execution = SqlExecutionResult(
        enabled=True,
        mode="sqlite",
        status="success",
        columns=["核销收入"],
        sample_rows=[],
        row_count=0,
        dry_run=False,
    )

    validation = ResultValidator().validate(
        sql="SELECT SUM(exe_income) AS 核销收入 FROM demo",
        query_plan=_plan("最近30天核销收入是多少？"),
        execution_result=execution,
    )
    advice = RepairPolicy().advise(
        execution_result=execution,
        result_validation=validation,
        safety_errors=[],
        sql_source="llm",
    )

    assert validation.passed is False
    assert "empty_result" in validation.errors
    assert "empty_result" in advice.categories
    assert advice.fallback_to_template is True


def test_result_validator_detects_all_null_metric_column():
    execution = SqlExecutionResult(
        enabled=True,
        mode="sqlite",
        status="success",
        columns=["核销收入"],
        sample_rows=[{"核销收入": None}, {"核销收入": None}],
        row_count=2,
        dry_run=False,
    )

    validation = ResultValidator().validate(
        sql="SELECT SUM(exe_income) AS 核销收入 FROM demo",
        query_plan=_plan("最近30天核销收入是多少？"),
        execution_result=execution,
    )

    assert validation.passed is False
    assert "all_null_metric_columns:核销收入" in validation.errors


def test_result_validator_accepts_semantic_equivalent_llm_aliases():
    query_plan = QueryPlan(
        intent="nl2sql",
        business_domain="连锁经管",
        original_question="最近30天北京奇迹胶原核销收入 TOP5门店",
        template_id="store_income_top10_30d",
        metrics=[
            MetricPlan(
                canonical="execution_income",
                display_name="核销收入",
                formula="SUM(exe_income)",
            )
        ],
        dimensions=[
            DimensionPlan(
                field="sy_hospital_name",
                alias="门店",
                source_table="dim_qy_tenant_info_all_d",
            )
        ],
    )
    execution = SqlExecutionResult(
        enabled=True,
        mode="maxcompute",
        status="success",
        columns=["sy_hospital_name", "total_income"],
        sample_rows=[
            {"sy_hospital_name": "新氧青春诊所(北京保利总部店) No.001", "total_income": "123.45"}
        ],
        row_count=1,
        dry_run=False,
    )

    validation = ResultValidator().validate(
        sql=(
            "SELECT t2.sy_hospital_name, SUM(t1.exe_income) AS total_income "
            "FROM demo t1 JOIN dim_tenant t2 ON t1.tenant_id = t2.tenant_id "
            "WHERE t2.city_name = '北京市' AND t1.standard_name = '奇迹胶原' "
            "GROUP BY t2.sy_hospital_name ORDER BY total_income DESC LIMIT 5"
        ),
        query_plan=query_plan,
        execution_result=execution,
    )

    assert validation.passed is True
    assert validation.errors == []


def test_result_validator_rejects_llm_sql_that_drops_question_constraints():
    query_plan = QueryPlan(
        intent="nl2sql",
        business_domain="连锁经管",
        original_question="最近30天北京奇迹胶原核销收入 TOP5门店",
        template_id="store_income_top10_30d",
        metrics=[
            MetricPlan(
                canonical="execution_income",
                display_name="核销收入",
                formula="SUM(exe_income)",
            )
        ],
    )
    execution = SqlExecutionResult(
        enabled=True,
        mode="maxcompute",
        status="success",
        columns=["total_exe_income"],
        sample_rows=[{"total_exe_income": "114061019.9554"}],
        row_count=1,
        dry_run=False,
    )

    validation = ResultValidator().validate(
        sql=(
            "SELECT SUM(exe_income) AS total_exe_income FROM demo "
            "WHERE is_valid = 1 ORDER BY total_exe_income DESC LIMIT 5"
        ),
        query_plan=query_plan,
        execution_result=execution,
    )

    assert validation.passed is False
    assert "missing_question_dimension:store:sy_hospital_name" in validation.errors
    assert "missing_question_filter:city_name" in validation.errors
    assert "missing_question_filter:standard_name" in validation.errors


class FailingExecutor(SqlExecutor):
    @property
    def mode(self) -> str:
        return "mock"

    @property
    def enabled(self) -> bool:
        return True

    def execute(self, request):
        return SqlExecutionResult(
            enabled=True,
            mode="mock",
            status="failed",
            sql=request.sql,
            error="simulated_unknown_field: no such column: bad_field",
        )


def test_pipeline_records_repair_attempt_when_execution_fails():
    pipeline = AskDataPipeline()
    pipeline.llm_sql_generator.enabled = False
    pipeline.executor = FailingExecutor()

    result = pipeline.run("最近30天各门店核销收入 TOP10")

    stage_names = [stage.name for stage in result.trace.stages]
    assert "execution" in stage_names
    assert "result_validation" in stage_names
    assert "repair_attempt" in stage_names
    assert result.result_validation.passed is False
    assert result.repair_attempt["attempted"] is True
    assert "execution_failed" in result.repair_attempt["advice"]["categories"]
