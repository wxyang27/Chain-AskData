from pathlib import Path
from typing import Any

import yaml


METRICS_REVIEWED_FILENAME = "metrics_from_feishu_dict.yaml"
FIELD_REVIEWED_SOURCES = [
    ("field_assets_from_feishu_prd.yaml", "feishu_prd_yaml"),
    ("field_assets_from_ddl_priority5.yaml", "ddl_priority5_yaml"),
]
CORE_FIELDS_PATH = Path("knowledge/schema/core_fields.yaml")


class ReviewedYamlAssetLoader:
    """Load manually reviewed YAML assets from docs/primary_knowledge."""

    def load(self, source_dir: Path) -> dict[str, list[dict[str, Any]]]:
        metrics_reviewed = self._load_reviewed_metrics(
            source_dir / METRICS_REVIEWED_FILENAME
        )
        fields_reviewed = self._load_reviewed_fields(source_dir)
        core_fields = self._load_core_fields()

        return {
            "metrics_reviewed": metrics_reviewed,
            "fields_reviewed": fields_reviewed,
            "core_fields_review_base": core_fields,
        }

    def merge_metrics(
        self,
        generated_metrics: list[dict[str, Any]],
        reviewed_metrics: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        merged = {
            metric["metric_id"]: metric
            for metric in generated_metrics
        }
        for metric in reviewed_metrics:
            merged[metric["metric_id"]] = metric
        return sorted(merged.values(), key=lambda item: item["metric_id"])

    def merge_fields(
        self,
        core_fields: list[dict[str, Any]],
        reviewed_fields: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        merged = {
            (field["table_name"], field["field_name"]): field
            for field in core_fields
        }
        for field in reviewed_fields:
            merged[(field["table_name"], field["field_name"])] = field
        return sorted(
            merged.values(),
            key=lambda item: (item["table_name"], item["field_name"]),
        )

    def _load_reviewed_metrics(self, path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        metrics = []
        for row in data.get("atomic_metrics", []):
            source_table = row.get("source_table", "")
            metrics.append(
                {
                    "asset_id": f"metric:{row['id']}",
                    "asset_type": "metric",
                    "metric_type": "atomic",
                    "metric_id": row["id"],
                    "name": row.get("name", ""),
                    "english_name": row.get("english", ""),
                    "business_domain": row.get("domain", ""),
                    "definition": row.get("definition", ""),
                    "formula": row.get("formula", ""),
                    "data_type": row.get("data_type", ""),
                    "unit": row.get("unit", ""),
                    "source_tables": [source_table] if source_table else [],
                    "sql": row.get("sql", ""),
                    "derived_metric_count": row.get("derived_count", ""),
                    "dashboard_names": [],
                    "notes": row.get("note", ""),
                    "review_status": "reviewed",
                    "source_kind": "feishu_dict_yaml",
                    "source_file": path.name,
                    "source_sheet": "atomic_metrics",
                    "source_row": row["id"],
                }
            )
        return metrics

    def _load_reviewed_fields(self, source_dir: Path) -> list[dict[str, Any]]:
        merged: dict[tuple[str, str], dict[str, Any]] = {}
        for filename, source_kind in FIELD_REVIEWED_SOURCES:
            path = source_dir / filename
            if not path.exists():
                continue
            for field in self._load_reviewed_fields_from_file(path, source_kind):
                merged[(field["table_name"], field["field_name"])] = field

        return sorted(
            merged.values(),
            key=lambda item: (item["table_name"], item["field_name"]),
        )

    def _load_reviewed_fields_from_file(
        self,
        path: Path,
        source_kind: str,
    ) -> list[dict[str, Any]]:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return [
            {
                "asset_id": f"field:{row['table_name']}:{row['field_name']}",
                "asset_type": "field",
                "table_name": row["table_name"],
                "full_table_name": row.get("full_table_name", ""),
                "field_name": row["field_name"],
                "field_type": row.get("field_type", ""),
                "business_name": row.get("business_name", ""),
                "description": row.get("description", ""),
                "used_by_metrics": row.get("used_by_metrics", []),
                "caliber": row.get("caliber", ""),
                "sample_values": row.get("sample_values", []),
                "enum_values": row.get("enum_values", []),
                "is_join_key": bool(row.get("is_join_key", False)),
                "is_metric_field": bool(row.get("is_metric_field", False)),
                "is_dimension_field": bool(row.get("is_dimension_field", False)),
                "filters": row.get("filters", []),
                "risk_notes": row.get("risk_notes", []),
                "review_status": "reviewed",
                "source_kind": source_kind,
                "source_file": path.name,
            }
            for row in data.get("fields", [])
        ]

    def _load_core_fields(self) -> list[dict[str, Any]]:
        if not CORE_FIELDS_PATH.exists():
            return []
        data = yaml.safe_load(CORE_FIELDS_PATH.read_text(encoding="utf-8")) or {}
        fields = []
        for row in data.get("fields", []):
            fields.append(
                {
                    "asset_id": f"field:{row['table_name']}:{row['field_name']}",
                    "asset_type": "field",
                    "table_name": row["table_name"],
                    "full_table_name": row.get("full_table_name", ""),
                    "field_name": row["field_name"],
                    "field_type": row.get("field_type", ""),
                    "business_name": row.get("business_name", ""),
                    "description": row.get("business_name", ""),
                    "used_by_metrics": row.get("used_by_metrics", []),
                    "caliber": row.get("caliber", ""),
                    "sample_values": [],
                    "enum_values": [],
                    "is_join_key": row.get("field_type") == "join_key",
                    "is_metric_field": row.get("field_type") in {"amount", "count_key"},
                    "is_dimension_field": row.get("field_type") == "dimension",
                    "filters": row.get("filters", []),
                    "risk_notes": row.get("risk_notes", []),
                    "review_status": "core",
                    "source_kind": "core_fields_yaml",
                    "source_file": str(CORE_FIELDS_PATH),
                }
            )
        return fields
