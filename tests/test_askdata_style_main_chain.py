from app.answer.composer import AnswerComposer
from app.knowledge_indexer.retrieval_context import RetrievalContext, RetrievalHit
from app.schema_retrieval.askdata_style_retriever import AskDataStyleSchemaRetriever


def test_askdata_style_schema_retriever_returns_main_schema_graph():
    context = RetrievalContext(
        query="exe_income by sy_hospital_name",
        fields=[
            RetrievalHit(
                document="field exe_income",
                metadata={
                    "asset_type": "field",
                    "field_id": "dm_opt_qy_user_execution_record_all_d.exe_income",
                    "field_name": "exe_income",
                    "table_name": "dm_opt_qy_user_execution_record_all_d",
                },
                distance=0.1,
                rerank_score=20.0,
            ),
            RetrievalHit(
                document="field sy_hospital_name",
                metadata={
                    "asset_type": "field",
                    "field_id": "dim_qy_tenant_info_all_d.sy_hospital_name",
                    "field_name": "sy_hospital_name",
                    "table_name": "dim_qy_tenant_info_all_d",
                },
                distance=0.1,
                rerank_score=19.0,
            ),
        ],
        metrics=[
            RetrievalHit(
                document="metric A002",
                metadata={"asset_type": "metric", "metric_id": "A002"},
                distance=0.1,
                rerank_score=18.0,
            )
        ],
    )

    result = AskDataStyleSchemaRetriever().retrieve(context)

    assert result["retriever"] == "askdata_style_schema_retriever"
    assert result["schema_graph"].relations
    assert "schema_graph_text" in result
    assert "dm_opt_qy_user_execution_record_all_d" in result["schema_graph_text"]
    assert "exe_income" in result["schema_graph_text"]


def test_answer_composer_uses_askdata_style_schema_graph_as_main_chain():
    response = AnswerComposer().compose("最近30天各门店核销收入 TOP10")

    assert response.schema_graph["retriever"] == "askdata_style_schema_retriever"
    assert "schema_graph_v2" not in response.schema_graph
    assert "ab_mode" not in response.schema_graph
    assert response.query_plan.query_plan_cot
    # Evidence now contains specific caliber notes, not a generic marker
    assert len(response.query_plan.query_plan_cot[0].evidence) >= 1

    # Verify four-tuple structure
    cot = response.query_plan.query_plan_cot[0]
    assert cot.step == 1
    assert cot.database == "soyoung_dw"
    # processing_objects may be empty when retrieval is sparse
    assert len(cot.operation_instructions) >= 2
    assert cot.output_target
    # Verify operation_instructions chain has filter and post-processing steps
    full_instructions = " ".join(cot.operation_instructions)
    assert "筛选" in full_instructions, f"Missing filter step in: {cot.operation_instructions}"
    assert (
        "关联" in full_instructions or "聚合" in full_instructions or "输出" in full_instructions
    ), f"Missing post-processing step in: {cot.operation_instructions}"
