from app.llm.query_plan_cot_validator import QueryPlanCoTValidator
from app.models.query import QueryPlanCoT
from app.schema_graph.graph import SchemaGraph


def _schema_graph() -> SchemaGraph:
    return SchemaGraph(
        query="最近30天各门店核销收入 TOP10",
        tables=[
            {"table_name": "execution_record"},
            {"table_name": "tenant_info"},
        ],
        fields=[
            {
                "table_name": "execution_record",
                "field_name": "exe_income",
            },
            {
                "table_name": "execution_record",
                "field_name": "tenant_id",
            },
            {
                "table_name": "tenant_info",
                "field_name": "tenant_id",
            },
            {
                "table_name": "tenant_info",
                "field_name": "sy_hospital_name",
            },
        ],
        relations=[
            {
                "source_table": "execution_record",
                "source_field": "tenant_id",
                "target_table": "tenant_info",
                "target_field": "tenant_id",
            }
        ],
    )


def _step(**overrides) -> QueryPlanCoT:
    values = {
        "step": 1,
        "database": "soyoung_dw",
        "processing_objects": [
            "execution_record.exe_income",
            "tenant_info.sy_hospital_name",
            "execution_record.tenant_id <-> tenant_info.tenant_id",
        ],
        "operation_instructions": [
            "先筛选有效核销记录",
            "再按 tenant_id 关联门店",
            "然后按门店聚合核销收入",
            "最后按核销收入降序输出 TOP10",
        ],
        "output_target": "sy_hospital_name、核销收入",
    }
    values.update(overrides)
    return QueryPlanCoT(**values)


def test_validator_accepts_grounded_query_plan_cot():
    result = QueryPlanCoTValidator().validate([_step()], _schema_graph())

    assert result.passed is True
    assert result.errors == []


def test_validator_rejects_unknown_field():
    result = QueryPlanCoTValidator().validate(
        [_step(processing_objects=["execution_record.imaginary_income"])],
        _schema_graph(),
    )

    assert result.passed is False
    assert "unknown_field:execution_record.imaginary_income" in result.errors


def test_validator_rejects_unknown_relation():
    result = QueryPlanCoTValidator().validate(
        [
            _step(
                processing_objects=[
                    "execution_record.exe_income",
                    "execution_record.exe_income <-> tenant_info.sy_hospital_name",
                ]
            )
        ],
        _schema_graph(),
    )

    assert result.passed is False
    assert any(error.startswith("unknown_relation:") for error in result.errors)


def test_validator_rejects_wrong_database_and_empty_output():
    result = QueryPlanCoTValidator().validate(
        [_step(database="invented_dw", output_target="")],
        _schema_graph(),
    )

    assert result.passed is False
    assert "unsupported_database:invented_dw" in result.errors
    assert "empty_output_target:step_1" in result.errors
