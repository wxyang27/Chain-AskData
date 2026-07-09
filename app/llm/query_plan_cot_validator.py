from dataclasses import dataclass, field

from app.models.query import QueryPlanCoT
from app.schema_graph.graph import SchemaGraph


@dataclass(frozen=True)
class QueryPlanCoTValidationResult:
    passed: bool
    errors: list[str] = field(default_factory=list)


class QueryPlanCoTValidator:
    """Validate LLM planning objects against the retrieved SchemaGraph."""

    def __init__(self, allowed_databases: set[str] | None = None):
        self.allowed_databases = allowed_databases or {"soyoung_dw"}

    def validate(
        self,
        steps: list[QueryPlanCoT],
        schema_graph: SchemaGraph,
    ) -> QueryPlanCoTValidationResult:
        errors: list[str] = []
        allowed_fields = self._allowed_fields(schema_graph)
        allowed_relations = self._allowed_relations(schema_graph)

        if not steps:
            errors.append("empty_steps")

        for step in steps:
            if step.database not in self.allowed_databases:
                errors.append(f"unsupported_database:{step.database}")
            if not step.output_target.strip():
                errors.append(f"empty_output_target:step_{step.step}")
            if not step.operation_instructions:
                errors.append(f"empty_operation_instructions:step_{step.step}")

            for processing_object in step.processing_objects:
                if "<->" in processing_object:
                    relation = self._parse_relation(processing_object)
                    if relation is None or relation not in allowed_relations:
                        errors.append(f"unknown_relation:{processing_object}")
                    continue

                field_name = self._normalize_field(processing_object)
                if field_name not in allowed_fields:
                    errors.append(f"unknown_field:{processing_object}")

        return QueryPlanCoTValidationResult(
            passed=not errors,
            errors=list(dict.fromkeys(errors)),
        )

    def _allowed_fields(self, schema_graph: SchemaGraph) -> set[str]:
        fields = set()
        for field in schema_graph.fields:
            table_name = str(field.get("table_name") or "").split(".")[-1]
            field_name = str(field.get("field_name") or "")
            if table_name and field_name:
                fields.add(f"{table_name}.{field_name}")
        return fields

    def _allowed_relations(
        self,
        schema_graph: SchemaGraph,
    ) -> set[tuple[str, str]]:
        relations = set()
        for relation in schema_graph.relations:
            source = self._field_pair(
                relation.get("source_table"),
                relation.get("source_field"),
            )
            target = self._field_pair(
                relation.get("target_table"),
                relation.get("target_field"),
            )
            if source and target:
                relations.add((source, target))
                relations.add((target, source))
        return relations

    def _parse_relation(self, value: str) -> tuple[str, str] | None:
        parts = [part.strip() for part in value.split("<->")]
        if len(parts) != 2:
            return None
        return self._normalize_field(parts[0]), self._normalize_field(parts[1])

    def _normalize_field(self, value: str) -> str:
        parts = value.strip().split(".")
        if len(parts) < 2:
            return value.strip()
        return ".".join(parts[-2:])

    def _field_pair(self, table_name, field_name) -> str:
        table = str(table_name or "").split(".")[-1]
        field = str(field_name or "")
        if not table or not field:
            return ""
        return f"{table}.{field}"
