from typing import Any

from app.knowledge_indexer.retrieval_context import RetrievalContext
from app.schema_graph.graph import SchemaGraph
from app.schema_index.loader import SchemaIndexBundle


class SchemaGraphBuilder:
    """Build a compact SchemaGraph from retrieval hits and schema indexes."""

    def __init__(self, schema_indexes: SchemaIndexBundle | None = None):
        self.schema_indexes = schema_indexes

    def build(self, retrieval_context: RetrievalContext) -> SchemaGraph:
        fields = self._enrich_fields(self._metadata_list(retrieval_context.fields))
        metrics = self._enrich_metrics(self._metadata_list(retrieval_context.metrics))
        tables = self._metadata_list(retrieval_context.tables)
        tables = self._merge_derived_tables(tables, fields)
        tables = self._merge_metric_tables(tables, metrics)
        tables = self._enrich_tables(tables)
        relations = self._merge_relations(
            self._metadata_list(retrieval_context.relations),
            tables,
        )

        missing_evidence = []
        if not fields:
            missing_evidence.append("fields")
        if not tables:
            missing_evidence.append("tables")
        if not metrics:
            missing_evidence.append("metrics")

        graph = SchemaGraph(
            query=retrieval_context.query,
            tables=tables,
            fields=fields,
            metrics=metrics,
            relations=relations,
            missing_evidence=missing_evidence,
        )

        return SchemaGraph(
            query=graph.query,
            tables=graph.tables,
            fields=graph.fields,
            metrics=graph.metrics,
            relations=graph.relations,
            missing_evidence=graph.missing_evidence,
            schema_graph_text=format_schema_graph(graph),
        )

    def _metadata_list(self, hits) -> list[dict[str, Any]]:
        return [hit.metadata for hit in hits]

    def _enrich_fields(self, fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not self.schema_indexes:
            return fields

        enriched = []
        seen = set()
        for field in fields:
            field_id = field.get("field_id") or self._field_id_from_metadata(field)
            detail = self.schema_indexes.field_detail_by_id.get(field_id, {})
            merged = {
                **field,
                **detail,
                "asset_type": "field",
            }
            if "full_name" not in merged:
                merged["full_name"] = self._field_full_name(merged)
            key = merged.get("field_id") or merged.get("full_name") or merged.get("field_name")
            if key and key in seen:
                continue
            if key:
                seen.add(key)
            enriched.append(merged)
        return enriched

    def _enrich_metrics(self, metrics: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not self.schema_indexes:
            return metrics

        enriched = []
        seen = set()
        for metric in metrics:
            metric_id = metric.get("metric_id") or metric.get("canonical")
            detail = self.schema_indexes.metric_rerank_by_id.get(metric_id, {})
            merged = {
                **metric,
                **detail,
                "asset_type": "metric",
            }
            if metric_id:
                merged.setdefault("metric_id", metric_id)
                merged.setdefault("canonical", metric_id)
            key = merged.get("metric_id") or merged.get("canonical")
            if key and key in seen:
                continue
            if key:
                seen.add(key)
            enriched.append(merged)
        return enriched

    def _merge_derived_tables(
        self,
        tables: list[dict[str, Any]],
        fields: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        merged = tables.copy()
        known = {
            table.get("table_name") or self._short_table_name(table.get("full_name", ""))
            for table in merged
        }
        for field in fields:
            table_name = field.get("table_name")
            full_name = field.get("full_table_name")
            key = table_name or self._short_table_name(full_name or "")
            if key and key not in known:
                merged.append(
                    {
                        "asset_type": "table",
                        "table_name": table_name or key,
                        "full_name": full_name or self._table_full_name(table_name or key),
                        "derived_from": "field",
                    }
                )
                known.add(key)
        return merged

    def _merge_metric_tables(
        self,
        tables: list[dict[str, Any]],
        metrics: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        merged = tables.copy()
        known = {
            table.get("table_name") or self._short_table_name(table.get("full_name", ""))
            for table in merged
        }
        for metric in metrics:
            for source_table in metric.get("source_tables", []) or []:
                table_name = self._short_table_name(source_table)
                if table_name and table_name not in known:
                    merged.append(
                        {
                            "asset_type": "table",
                            "table_name": table_name,
                            "full_name": source_table,
                            "derived_from": "metric",
                        }
                    )
                    known.add(table_name)
        return merged

    def _enrich_tables(self, tables: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not self.schema_indexes:
            return tables

        enriched = []
        seen = set()
        for table in tables:
            table_name = table.get("table_name") or self._short_table_name(table.get("full_name", ""))
            detail = self.schema_indexes.table_by_name.get(table_name, {})
            merged = {
                **table,
                **detail,
                "asset_type": "table",
            }
            if table_name:
                merged.setdefault("table_name", table_name)
                merged.setdefault("full_name", self._table_full_name(table_name))
            key = merged.get("table_name") or merged.get("full_name")
            if key and key in seen:
                continue
            if key:
                seen.add(key)
            enriched.append(merged)
        return enriched

    def _merge_relations(
        self,
        relations: list[dict[str, Any]],
        tables: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        merged = [self._normalize_relation(relation) for relation in relations]
        if self.schema_indexes:
            table_names = [
                table.get("table_name") or self._short_table_name(table.get("full_name", ""))
                for table in tables
            ]
            merged.extend(self.schema_indexes.get_relations_for_tables(table_names))

        deduped = []
        seen = set()
        for relation in merged:
            key = (
                relation.get("source_table"),
                relation.get("source_field"),
                relation.get("target_table"),
                relation.get("target_field"),
            )
            if key in seen:
                continue
            seen.add(key)
            deduped.append(relation)
        return deduped

    def _normalize_relation(self, relation: dict[str, Any]) -> dict[str, Any]:
        if "source_table" in relation:
            return relation
        return {
            **relation,
            "source_table": relation.get("left_table", ""),
            "source_field": relation.get("left_field", relation.get("join_key", "")),
            "target_table": relation.get("right_table", ""),
            "target_field": relation.get("right_field", relation.get("join_key", "")),
            "relation_description": relation.get("usage", ""),
        }

    def _field_id_from_metadata(self, field: dict[str, Any]) -> str:
        table_name = field.get("table_name")
        field_name = field.get("field_name")
        if table_name and field_name:
            return f"{table_name}.{field_name}"
        return ""

    def _field_full_name(self, field: dict[str, Any]) -> str:
        database_name = field.get("database_name") or "soyoung_dw"
        table_name = field.get("table_name", "")
        field_name = field.get("field_name", "")
        if table_name and field_name:
            return f"{database_name}.{table_name}.{field_name}"
        return field_name

    def _table_full_name(self, table_name: str) -> str:
        if "." in table_name:
            return table_name
        return f"soyoung_dw.{table_name}"

    def _short_table_name(self, table_name: str) -> str:
        return table_name.split(".")[-1] if table_name else ""


def format_schema_graph(schema_graph: SchemaGraph) -> str:
    """Format SchemaGraph as prompt-ready local schema text."""

    lines = [f"Query: {schema_graph.query}"]
    table_map = {
        table.get("table_name") or table.get("full_name"): table
        for table in schema_graph.tables
    }
    fields_by_table: dict[str, list[dict[str, Any]]] = {}
    for field in schema_graph.fields:
        table_name = field.get("table_name", "")
        fields_by_table.setdefault(table_name, []).append(field)

    for table_name, fields in fields_by_table.items():
        table = table_map.get(table_name, {})
        lines.append("")
        lines.append(f"Table: {table.get('full_name') or table_name}")
        lines.append(f"Table Summary: {table.get('table_summary', '')}")

        for field in fields:
            lines.append(f"Field: {field.get('field_name', '')}")
            lines.append(f"Field Type: {field.get('field_type', '')}")
            lines.append(f"Business Name: {field.get('business_name', '')}")
            lines.append(f"Description: {field.get('field_description', '')}")
            lines.append(f"Caliber: {field.get('caliber', '')}")
            lines.append(
                "Sample/Range: "
                f"{field.get('sample_values', '')}; {field.get('value_range', '')}"
            )

    if schema_graph.metrics:
        lines.append("")
        lines.append("Metrics:")
        for metric in schema_graph.metrics:
            metric_id = metric.get("metric_id") or metric.get("canonical", "")
            metric_name = metric.get("metric_name") or metric.get("display_name", "")
            lines.append(f"- {metric_id}: {metric_name}")

    lines.append("")
    lines.append("Relations:")
    if not schema_graph.relations:
        lines.append("- None")
    else:
        for relation in schema_graph.relations:
            lines.append(
                "Relation: "
                f"{relation.get('source_table', '')}.{relation.get('source_field', '')} -> "
                f"{relation.get('target_table', '')}.{relation.get('target_field', '')}"
            )
            description = relation.get("relation_description") or relation.get("usage", "")
            if description:
                lines.append(f"Relation Description: {description}")

    if schema_graph.missing_evidence:
        lines.append("")
        lines.append("Missing Evidence:")
        for item in schema_graph.missing_evidence:
            lines.append(f"- {item}")

    return "\n".join(lines)
