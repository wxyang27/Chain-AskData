from typing import Any

from app.knowledge_indexer.retrieval_context import RetrievalContext
from app.schema_graph.graph import SchemaGraph


class SchemaGraphBuilder:
    """Build a compact schema graph from RetrievalContext."""

    def build(self, retrieval_context: RetrievalContext) -> SchemaGraph:
        fields = self._metadata_list(retrieval_context.fields)
        tables = self._metadata_list(retrieval_context.tables)
        tables = self._merge_derived_tables(tables, fields)
        metrics = self._metadata_list(retrieval_context.metrics)
        relations = self._metadata_list(retrieval_context.relations)

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
            schema_graph_text=self._format_graph_text(graph),
        )

    def _metadata_list(self, hits) -> list[dict[str, Any]]:
        return [hit.metadata for hit in hits]

    def _merge_derived_tables(
        self,
        tables: list[dict[str, Any]],
        fields: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        merged = tables.copy()
        known = {
            table.get("table_name") or table.get("full_name")
            for table in merged
        }
        for field in fields:
            table_name = field.get("table_name")
            full_name = field.get("full_table_name")
            key = table_name or full_name
            if key and key not in known:
                merged.append(
                    {
                        "asset_type": "table",
                        "table_name": table_name,
                        "full_name": full_name,
                        "derived_from": "field",
                    }
                )
                known.add(key)
        return merged

    def _format_graph_text(self, graph: SchemaGraph) -> str:
        lines = [f"Query: {graph.query}", "Tables:"]
        for table in graph.tables:
            lines.append(
                f"- {table.get('full_name') or table.get('table_name')}"
            )

        lines.append("Fields:")
        for field in graph.fields:
            full_name = field.get("full_name") or field.get("field_name")
            business_name = field.get("business_name") or ""
            lines.append(f"- {full_name}: {business_name}")

        lines.append("Metrics:")
        for metric in graph.metrics:
            lines.append(
                f"- {metric.get('canonical') or metric.get('display_name')}"
            )

        lines.append("Relations:")
        for relation in graph.relations:
            left = relation.get("left_table", "")
            right = relation.get("right_table", "")
            usage = relation.get("usage", "")
            lines.append(f"- {left} -> {right}: {usage}")

        if graph.missing_evidence:
            lines.append("Missing Evidence:")
            for item in graph.missing_evidence:
                lines.append(f"- {item}")

        return "\n".join(lines)
