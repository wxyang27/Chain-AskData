import json
from pathlib import Path

from app.knowledge_importer.pipeline import PrimaryKnowledgeImporter


def test_imports_uploaded_primary_knowledge_into_structured_assets(tmp_path):
    source_dir = Path("docs/primary_knowledge")
    assert source_dir.exists()

    result = PrimaryKnowledgeImporter().import_to_directory(source_dir, tmp_path)

    assert result.counts["metrics"] == 151
    assert result.counts["user_profile_fields"] == 112
    assert result.counts["dimensions"] == 10
    assert result.counts["data_sources"] == 7
    assert result.counts["dashboard_metrics"] == 288
    assert result.counts["tables"] >= 49
    assert result.counts["business_playbooks"] > 10

    metrics = json.loads((tmp_path / "metrics_full.json").read_text(encoding="utf-8"))
    metric_by_id = {metric["metric_id"]: metric for metric in metrics}
    assert metric_by_id["A002"]["name"] == "核销收入"
    assert "exe_income" in metric_by_id["A002"]["sql"]
    assert metric_by_id["A005"]["name"] == "核销人数"
    assert "customer_id" in metric_by_id["A005"]["sql"]

    tables = json.loads((tmp_path / "tables_full.json").read_text(encoding="utf-8"))
    table_names = {table["table_name"] for table in tables}
    assert "dws_opt_qy_core_summary_all_d" in table_names
    assert "dm_opt_qy_user_execution_record_all_d" in table_names

    playbooks = json.loads(
        (tmp_path / "business_playbooks.json").read_text(encoding="utf-8")
    )
    playbook_text = "\n".join(item["content"] for item in playbooks)
    assert "收入 = 核销人次 x 客单价" in playbook_text
