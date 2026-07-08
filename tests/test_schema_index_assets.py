import json
from pathlib import Path

from app.knowledge_importer.pipeline import PrimaryKnowledgeImporter


def test_importer_writes_consolidated_assets_directory(tmp_path):
    result = PrimaryKnowledgeImporter().import_to_directory(
        Path("docs/primary_knowledge"),
        tmp_path,
    )

    assets_dir = tmp_path / "assets"
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))

    assert result.counts["assets_metrics"] == 151
    assert result.counts["assets_fields"] == 135
    assert result.counts["assets_tables"] == 49
    assert result.counts["assets_dimensions"] == 10
    assert manifest["assets"]["metrics"] == 151
    assert manifest["assets"]["fields"] == 135

    assert len(json.loads((assets_dir / "metrics.json").read_text(encoding="utf-8"))) == 151
    assert len(json.loads((assets_dir / "fields.json").read_text(encoding="utf-8"))) == 135
    assert len(json.loads((assets_dir / "tables.json").read_text(encoding="utf-8"))) == 49
    assert len(json.loads((assets_dir / "dimensions.json").read_text(encoding="utf-8"))) == 10

    business_assets = json.loads(
        (assets_dir / "business_assets.json").read_text(encoding="utf-8")
    )
    assert len(business_assets["data_sources"]) == 7
    assert len(business_assets["dashboard_metrics"]) == 288
    assert len(business_assets["business_playbooks"]) == 81
    assert len(business_assets["user_profile_fields"]) == 112


def test_importer_writes_askdata_style_schema_indexes(tmp_path):
    PrimaryKnowledgeImporter().import_to_directory(
        Path("docs/primary_knowledge"),
        tmp_path,
    )

    indexes_dir = tmp_path / "indexes"
    field_keyword = json.loads(
        (indexes_dir / "schema_field_keyword_index.json").read_text(encoding="utf-8")
    )
    field_vector = json.loads(
        (indexes_dir / "schema_field_vector_index.json").read_text(encoding="utf-8")
    )
    field_rerank = json.loads(
        (indexes_dir / "schema_field_rerank_index.json").read_text(encoding="utf-8")
    )
    field_detail = json.loads(
        (indexes_dir / "schema_field_detail_index.json").read_text(encoding="utf-8")
    )
    table_index = json.loads(
        (indexes_dir / "schema_table_index.json").read_text(encoding="utf-8")
    )
    relation_index = json.loads(
        (indexes_dir / "schema_relation_index.json").read_text(encoding="utf-8")
    )
    metric_keyword = json.loads(
        (indexes_dir / "metric_keyword_index.json").read_text(encoding="utf-8")
    )
    metric_rerank = json.loads(
        (indexes_dir / "metric_rerank_index.json").read_text(encoding="utf-8")
    )

    assert len(field_keyword) == 135
    assert len(field_vector) == 135
    assert len(field_rerank) == 135
    assert len(field_detail) == 135
    assert len(table_index) == 49
    assert len(relation_index) >= 2
    assert len(metric_keyword) == 151
    assert len(metric_rerank) == 151

    exe_income = next(item for item in field_keyword if item["field_name"] == "exe_income")
    assert exe_income["field_id"] == "dm_opt_qy_user_execution_record_all_d.exe_income"
    assert "exe_income" in exe_income["keyword_text"]
    assert "dm_opt_qy_user_execution_record_all_d" in exe_income["table_name"]

    metric_a002 = next(item for item in metric_keyword if item["metric_id"] == "A002")
    assert metric_a002["asset_type"] == "metric"
    assert "exe_income" in metric_a002["keyword_text"]
