import json
from pathlib import Path

from app.knowledge_importer.pipeline import PrimaryKnowledgeImporter
from app.knowledge_importer.chunker import load_generated_knowledge_chunks


def test_importer_merges_reviewed_metric_and_field_assets(tmp_path):
    result = PrimaryKnowledgeImporter().import_to_directory(
        Path("docs/primary_knowledge"),
        tmp_path,
    )

    assert result.counts["metrics_reviewed"] == 19
    assert result.counts["fields_reviewed"] == 107
    assert result.counts["metrics_merged"] == 151
    assert result.counts["fields_merged"] == 135

    metrics = json.loads((tmp_path / "metrics_merged.json").read_text(encoding="utf-8"))
    metric_by_id = {metric["metric_id"]: metric for metric in metrics}
    assert metric_by_id["A002"]["review_status"] == "reviewed"
    assert metric_by_id["A002"]["source_kind"] == "feishu_dict_yaml"
    assert metric_by_id["A002"]["name"] == "核销收入"
    assert "exe_income" in metric_by_id["A002"]["sql"]

    fields = json.loads((tmp_path / "fields_merged.json").read_text(encoding="utf-8"))
    field_by_key = {
        (field["table_name"], field["field_name"]): field
        for field in fields
    }
    assert (
        "dm_opt_qy_user_summary_info_all_d",
        "user_id",
    ) in field_by_key
    assert field_by_key[
        ("dm_opt_qy_user_summary_info_all_d", "user_id")
    ]["source_kind"] == "ddl_priority5_yaml"
    assert (
        "dws_opt_qy_core_summary_all_d",
        "tenant_id",
    ) in field_by_key
    assert field_by_key[
        ("dm_opt_qy_user_execution_record_all_d", "exe_income")
    ]["source_kind"] == "core_fields_yaml"


def test_generated_chunks_prefer_merged_reviewed_assets(tmp_path):
    PrimaryKnowledgeImporter().import_to_directory(
        Path("docs/primary_knowledge"),
        tmp_path,
    )

    chunks = load_generated_knowledge_chunks(tmp_path)
    metric_a002 = [
        chunk
        for chunk in chunks
        if chunk.chunk_id == "generated_metric:A002"
    ]
    user_id_field = [
        chunk
        for chunk in chunks
        if chunk.chunk_id
        == "generated_schema_field:dm_opt_qy_user_summary_info_all_d:user_id"
    ]

    assert len(metric_a002) == 1
    assert metric_a002[0].metadata["review_status"] == "reviewed"
    assert len(user_id_field) == 1
    assert user_id_field[0].metadata["asset_type"] == "field"
    assert user_id_field[0].metadata["source_kind"] == "ddl_priority5_yaml"
