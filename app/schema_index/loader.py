import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REQUIRED_INDEX_FILES = {
    "schema_field_keyword_index": "schema_field_keyword_index.json",
    "schema_field_vector_index": "schema_field_vector_index.json",
    "schema_field_rerank_index": "schema_field_rerank_index.json",
    "schema_table_index": "schema_table_index.json",
    "schema_field_detail_index": "schema_field_detail_index.json",
    "schema_relation_index": "schema_relation_index.json",
    "metric_keyword_index": "metric_keyword_index.json",
    "metric_rerank_index": "metric_rerank_index.json",
}


@dataclass(frozen=True)
class SchemaIndexBundle:
    """In-memory access layer for AskData-style schema indexes."""

    indexes_dir: Path
    schema_field_keyword_index: list[dict[str, Any]]
    schema_field_vector_index: list[dict[str, Any]]
    schema_field_rerank_index: list[dict[str, Any]]
    schema_table_index: list[dict[str, Any]]
    schema_field_detail_index: list[dict[str, Any]]
    schema_relation_index: list[dict[str, Any]]
    metric_keyword_index: list[dict[str, Any]]
    metric_rerank_index: list[dict[str, Any]]

    @property
    def field_detail_by_id(self) -> dict[str, dict[str, Any]]:
        return {
            item["field_id"]: item
            for item in self.schema_field_detail_index
        }

    @property
    def field_rerank_by_id(self) -> dict[str, dict[str, Any]]:
        return {
            item["field_id"]: item
            for item in self.schema_field_rerank_index
        }

    @property
    def table_by_name(self) -> dict[str, dict[str, Any]]:
        return {
            item["table_name"]: item
            for item in self.schema_table_index
        }

    @property
    def metric_rerank_by_id(self) -> dict[str, dict[str, Any]]:
        return {
            item["metric_id"]: item
            for item in self.metric_rerank_index
        }

    def get_field_detail(self, field_id: str) -> dict[str, Any]:
        return self.field_detail_by_id[field_id]

    def get_field_rerank(self, field_id: str) -> dict[str, Any]:
        return self.field_rerank_by_id[field_id]

    def get_table(self, table_name: str) -> dict[str, Any]:
        return self.table_by_name[table_name]

    def get_metric_rerank(self, metric_id: str) -> dict[str, Any]:
        return self.metric_rerank_by_id[metric_id]

    def get_relations_for_tables(self, table_names: list[str]) -> list[dict[str, Any]]:
        table_set = set(table_names)
        return [
            relation
            for relation in self.schema_relation_index
            if relation.get("source_table") in table_set
            and relation.get("target_table") in table_set
        ]


class SchemaIndexLoader:
    """Load generated AskData-style schema index JSON files."""

    def load(
        self,
        indexes_dir: Path | str = Path("knowledge/generated/indexes"),
    ) -> SchemaIndexBundle:
        indexes_dir = Path(indexes_dir)
        missing_files = [
            filename
            for filename in REQUIRED_INDEX_FILES.values()
            if not (indexes_dir / filename).exists()
        ]
        if missing_files:
            missing = ", ".join(missing_files)
            raise FileNotFoundError(
                f"Missing schema index files in {indexes_dir}: {missing}"
            )

        payloads = {
            name: self._load_json(indexes_dir / filename)
            for name, filename in REQUIRED_INDEX_FILES.items()
        }
        return SchemaIndexBundle(
            indexes_dir=indexes_dir,
            schema_field_keyword_index=payloads["schema_field_keyword_index"],
            schema_field_vector_index=payloads["schema_field_vector_index"],
            schema_field_rerank_index=payloads["schema_field_rerank_index"],
            schema_table_index=payloads["schema_table_index"],
            schema_field_detail_index=payloads["schema_field_detail_index"],
            schema_relation_index=payloads["schema_relation_index"],
            metric_keyword_index=payloads["metric_keyword_index"],
            metric_rerank_index=payloads["metric_rerank_index"],
        )

    def _load_json(self, path: Path) -> list[dict[str, Any]]:
        return json.loads(path.read_text(encoding="utf-8"))
