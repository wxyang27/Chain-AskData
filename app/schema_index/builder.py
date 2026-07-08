from pathlib import Path
from typing import Any

from app.assets.loader import load_yaml_asset


class SchemaIndexBuilder:
    """Build AskData-style retrieval, rerank, and SchemaGraph index records."""

    def build(
        self,
        metrics: list[dict[str, Any]],
        fields: list[dict[str, Any]],
        tables: list[dict[str, Any]],
    ) -> dict[str, list[dict[str, Any]]]:
        return {
            "schema_field_keyword_index.json": self._field_keyword_index(fields),
            "schema_field_vector_index.json": self._field_vector_index(fields),
            "schema_field_rerank_index.json": self._field_rerank_index(fields),
            "schema_table_index.json": self._table_index(tables),
            "schema_field_detail_index.json": self._field_detail_index(fields),
            "schema_relation_index.json": self._relation_index(),
            "metric_keyword_index.json": self._metric_keyword_index(metrics),
            "metric_rerank_index.json": self._metric_rerank_index(metrics),
        }

    def _field_keyword_index(self, fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
        rows = []
        for field in fields:
            rows.append(
                {
                    "field_id": self._field_id(field),
                    "database_name": self._database_name(field),
                    "table_name": field["table_name"],
                    "field_name": field["field_name"],
                    "field_description": field.get("description", ""),
                    "table_description": "",
                    "keyword_text": self._join_text(
                        [
                            field.get("field_name", ""),
                            field.get("business_name", ""),
                            field.get("description", ""),
                            field.get("caliber", ""),
                            field.get("field_type", ""),
                            field.get("used_by_metrics", []),
                            field.get("risk_notes", []),
                        ]
                    ),
                    "source_kind": field.get("source_kind", ""),
                }
            )
        return rows

    def _field_vector_index(self, fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
        rows = []
        for field in fields:
            rows.append(
                {
                    "field_id": self._field_id(field),
                    "database_name": self._database_name(field),
                    "table_name": field["table_name"],
                    "field_name": field["field_name"],
                    "field_description": field.get("description", ""),
                    "table_description": "",
                    "vector_text": self._join_text(
                        [
                            f"字段 {field.get('field_name', '')}",
                            f"业务含义 {field.get('business_name', '')}",
                            f"字段说明 {field.get('description', '')}",
                            f"口径 {field.get('caliber', '')}",
                            f"过滤 {field.get('filters', [])}",
                        ]
                    ),
                    "source_kind": field.get("source_kind", ""),
                }
            )
        return rows

    def _field_rerank_index(self, fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
        rows = []
        for field in fields:
            rows.append(
                {
                    "field_id": self._field_id(field),
                    "database_name": self._database_name(field),
                    "table_name": field["table_name"],
                    "field_name": field["field_name"],
                    "field_type": field.get("field_type", ""),
                    "field_description": field.get("description", ""),
                    "table_description": "",
                    "rerank_text": self._field_rerank_text(field),
                    "source_kind": field.get("source_kind", ""),
                }
            )
        return rows

    def _table_index(self, tables: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                "database_name": self._database_from_full_name(table.get("full_name", "")),
                "table_name": table["table_name"],
                "full_name": table.get("full_name", ""),
                "layer": table.get("layer", ""),
                "theme": table.get("theme", ""),
                "grain": table.get("grain", ""),
                "partition_field": table.get("partition_field", ""),
                "table_summary": self._join_text(
                    [
                        table.get("business_description", ""),
                        table.get("theme", ""),
                        table.get("grain", ""),
                        table.get("main_fields", []),
                    ]
                ),
            }
            for table in tables
        ]

    def _field_detail_index(self, fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                "field_id": self._field_id(field),
                "database_name": self._database_name(field),
                "table_name": field["table_name"],
                "field_name": field["field_name"],
                "field_type": field.get("field_type", ""),
                "field_description": field.get("description", ""),
                "business_name": field.get("business_name", ""),
                "caliber": field.get("caliber", ""),
                "sample_values": field.get("sample_values", []),
                "value_range": field.get("enum_values", []),
                "filters": field.get("filters", []),
                "risk_notes": field.get("risk_notes", []),
                "is_join_key": field.get("is_join_key", False),
                "is_metric_field": field.get("is_metric_field", False),
                "is_dimension_field": field.get("is_dimension_field", False),
            }
            for field in fields
        ]

    def _relation_index(self) -> list[dict[str, Any]]:
        asset = load_yaml_asset("knowledge/relations/table_relations.yaml")
        rows = []
        for relation in asset.get("relations", []):
            source_table = self._short_table_name(relation.get("left_table", ""))
            target_table = self._short_table_name(relation.get("right_table", ""))
            join_keys = relation.get("join_keys", [])
            source_field = join_keys[0] if join_keys else ""
            rows.append(
                {
                    "source_table": source_table,
                    "source_field": source_field,
                    "target_table": target_table,
                    "target_field": source_field,
                    "relation_type": relation.get("join_type", ""),
                    "condition": relation.get("condition", ""),
                    "relation_description": relation.get("usage", ""),
                }
            )
        return rows

    def _metric_keyword_index(self, metrics: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                "asset_type": "metric",
                "metric_id": metric["metric_id"],
                "metric_name": metric.get("name", ""),
                "metric_type": metric.get("metric_type", ""),
                "source_tables": metric.get("source_tables", []),
                "keyword_text": self._join_text(
                    [
                        metric.get("metric_id", ""),
                        metric.get("name", ""),
                        metric.get("english_name", ""),
                        metric.get("definition", ""),
                        metric.get("formula", ""),
                        metric.get("source_tables", []),
                        metric.get("sql", ""),
                        metric.get("notes", ""),
                    ]
                ),
            }
            for metric in metrics
        ]

    def _metric_rerank_index(self, metrics: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                "asset_type": "metric",
                "metric_id": metric["metric_id"],
                "metric_name": metric.get("name", ""),
                "metric_type": metric.get("metric_type", ""),
                "source_tables": metric.get("source_tables", []),
                "rerank_text": self._join_text(
                    [
                        f"指标：{metric.get('name', '')}",
                        f"指标编码：{metric.get('metric_id', '')}",
                        f"指标类型：{metric.get('metric_type', '')}",
                        f"定义：{metric.get('definition', '')}",
                        f"公式：{metric.get('formula', '')}",
                        f"来源表：{metric.get('source_tables', [])}",
                        f"SQL：{metric.get('sql', '')}",
                        f"备注：{metric.get('notes', '')}",
                    ]
                ),
            }
            for metric in metrics
        ]

    def _field_rerank_text(self, field: dict[str, Any]) -> str:
        return self._join_text(
            [
                f"字段：{field.get('field_name', '')}",
                f"业务含义：{field.get('business_name', '')}",
                f"来源表：{field.get('full_table_name', '')}",
                f"字段类型：{field.get('field_type', '')}",
                f"字段说明：{field.get('description', '')}",
                f"口径：{field.get('caliber', '')}",
                f"过滤：{field.get('filters', [])}",
                f"易错提醒：{field.get('risk_notes', [])}",
            ]
        )

    def _field_id(self, field: dict[str, Any]) -> str:
        return f"{field['table_name']}.{field['field_name']}"

    def _database_name(self, field: dict[str, Any]) -> str:
        return self._database_from_full_name(field.get("full_table_name", ""))

    def _database_from_full_name(self, full_name: str) -> str:
        if "." in full_name:
            return full_name.split(".", 1)[0]
        return "soyoung_dw"

    def _short_table_name(self, table_name: str) -> str:
        return table_name.split(".")[-1]

    def _join_text(self, values: list[Any]) -> str:
        parts: list[str] = []
        for value in values:
            if isinstance(value, list):
                parts.extend(str(item) for item in value if item)
            elif value:
                parts.append(str(value))
        return " ".join(parts)
