from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SchemaGraph:
    query: str
    tables: list[dict[str, Any]] = field(default_factory=list)
    fields: list[dict[str, Any]] = field(default_factory=list)
    metrics: list[dict[str, Any]] = field(default_factory=list)
    relations: list[dict[str, Any]] = field(default_factory=list)
    missing_evidence: list[str] = field(default_factory=list)
    schema_graph_text: str = ""

    @property
    def table_names(self) -> list[str]:
        return [
            str(table.get("table_name") or table.get("full_name"))
            for table in self.tables
            if table.get("table_name") or table.get("full_name")
        ]

    @property
    def field_names(self) -> list[str]:
        return [
            str(field.get("field_name"))
            for field in self.fields
            if field.get("field_name")
        ]

    @property
    def metric_ids(self) -> list[str]:
        return [
            str(metric.get("metric_id") or metric.get("canonical"))
            for metric in self.metrics
            if metric.get("metric_id") or metric.get("canonical")
        ]

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "tables": self.tables,
            "fields": self.fields,
            "metrics": self.metrics,
            "relations": self.relations,
            "missing_evidence": self.missing_evidence,
            "schema_graph_text": self.schema_graph_text,
        }
