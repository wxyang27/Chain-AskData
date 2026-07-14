from pathlib import Path

import pytest

from app.knowledge_importer.pipeline import PrimaryKnowledgeImporter
from app.schema_indexing.loader import SchemaIndexLoader


def test_schema_index_loader_loads_all_askdata_style_indexes(tmp_path):
    PrimaryKnowledgeImporter().import_to_directory(
        Path("docs/primary_knowledge"),
        tmp_path,
    )

    bundle = SchemaIndexLoader().load(tmp_path / "indexes")

    assert len(bundle.schema_field_keyword_index) == 134
    assert len(bundle.schema_field_vector_index) == 134
    assert len(bundle.schema_field_rerank_index) == 134
    assert len(bundle.schema_field_detail_index) == 134
    assert len(bundle.schema_table_index) == 49
    assert len(bundle.schema_relation_index) >= 2
    assert len(bundle.metric_keyword_index) == 151
    assert len(bundle.metric_rerank_index) == 151

    field = bundle.get_field_detail("dm_opt_qy_user_execution_record_all_d.exe_income")
    assert field["field_name"] == "exe_income"
    assert field["table_name"] == "dm_opt_qy_user_execution_record_all_d"

    table = bundle.get_table("dm_opt_qy_user_execution_record_all_d")
    assert table["full_name"] == "soyoung_dw.dm_opt_qy_user_execution_record_all_d"

    metric = bundle.get_metric_rerank("A002")
    assert metric["metric_id"] == "A002"
    assert "exe_income" in metric["rerank_text"]

    relations = bundle.get_relations_for_tables(
        [
            "dm_opt_qy_user_execution_record_all_d",
            "dim_qy_tenant_info_all_d",
        ]
    )
    assert any(relation["target_table"] == "dim_qy_tenant_info_all_d" for relation in relations)


def test_schema_index_loader_reports_missing_index_files(tmp_path):
    with pytest.raises(FileNotFoundError, match="schema_field_keyword_index.json"):
        SchemaIndexLoader().load(tmp_path)
