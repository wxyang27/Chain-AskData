from dataclasses import dataclass, field

from app.models.query import QueryPlanCoT
from app.schema_graph.graph import SchemaGraph


@dataclass(frozen=True)
class QueryPlanCoTValidationResult:
    passed: bool
    errors: list[str] = field(default_factory=list)


class QueryPlanCoTValidator:
    """Validate LLM planning objects against the retrieved SchemaGraph.

    Checks (in order):
    1. Structural: non-empty steps, allowed database, non-empty output/instructions
    2. Field existence: every table.field in processing_objects must be in SchemaGraph
    3. Relation existence: every <-> relation must be in SchemaGraph
    4. Cross-table integrity: when instructions mention joining, relations must exist
    5. Output grounding: output_target fields/aggregates must reference processing_objects
    """

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
            # --- structural checks ---
            if step.database not in self.allowed_databases:
                errors.append(f"unsupported_database:{step.database}")
            if not step.output_target.strip():
                errors.append(f"empty_output_target:step_{step.step}")
            if not step.operation_instructions:
                errors.append(f"empty_operation_instructions:step_{step.step}")
            if not step.processing_objects:
                errors.append(f"empty_processing_objects:step_{step.step}")

            # --- field & relation existence ---
            step_fields: set[str] = set()
            step_relations: list[tuple[str, str]] = []

            for processing_object in step.processing_objects:
                if "<->" in processing_object:
                    relation = self._parse_relation(processing_object)
                    if relation is None or relation not in allowed_relations:
                        errors.append(f"unknown_relation:{processing_object}")
                    else:
                        step_relations.append(relation)
                    continue

                field_name = self._normalize_field(processing_object)
                if field_name not in allowed_fields:
                    errors.append(f"unknown_field:{processing_object}")
                else:
                    step_fields.add(field_name)

            # --- cross-table integrity ---
            has_join_instruction = any(
                self._mentions_real_join(instr)
                for instr in step.operation_instructions
            )
            has_relations_in_objects = bool(step_relations)

            relation_optional = self._is_target_progress_metric(step_fields)
            if has_join_instruction and not has_relations_in_objects and not relation_optional:
                if not schema_graph.relations:
                    errors.append(
                        f"cross_table_no_relations:step_{step.step}"
                        f"_tables={step_fields}"
                    )

            # --- output grounding ---
            output_tokens = self._extract_output_field_tokens(step.output_target)
            for token in output_tokens:
                if not self._looks_like_field_reference(token):
                    continue
                # Match by full "table.field" or by field name alone
                matched = (
                    token in step_fields
                    or any(f.endswith(f".{token}") for f in step_fields)
                    or token in self._instruction_tokens(step.operation_instructions)
                )
                if not matched:
                    errors.append(
                        f"output_not_in_processing:step_{step.step}:{token}"
                    )

        return QueryPlanCoTValidationResult(
            passed=not errors,
            errors=list(dict.fromkeys(errors)),
        )

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

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

    def _extract_output_field_tokens(self, output_target: str) -> set[str]:
        """Extract candidate field references from output_target text."""
        import re

        tokens: set[str] = set()
        # Remove bracket/quotes/descriptions: "门店（['sy_hospital_name']）" → "门店 sy_hospital_name"
        cleaned = re.sub(r"[（(]['\"]?\[?|]?['\"]?[）)]", " ", output_target)
        # Remove common aggregation wrappers and keep field names
        cleaned = re.sub(
            r"(?:SUM|COUNT|AVG|MAX|MIN)\s*\(\s*(?:DISTINCT\s+)?(\w+(?:\.\w+)?)\s*\)",
            r"\1", cleaned, flags=re.IGNORECASE,
        )
        # Split on separators
        for part in re.split(r"[、，,;；\s/]+", cleaned):
            part = part.strip().strip("'\"[]（）()")
            if part and not part.upper() in ("SUM", "COUNT", "AVG", "MAX", "MIN",
                                              "DISTINCT", "AS", "GROUP", "BY", "ORDER"):
                tokens.add(part)
        return tokens - {""}

    def _instruction_tokens(self, instructions: list[str]) -> set[str]:
        """Collect field-like tokens from operation instructions."""
        tokens: set[str] = set()
        for instr in instructions:
            for part in instr.replace("、", ",").replace("，", ",").split(","):
                part = part.strip()
                if "." in part:
                    tokens.add(self._normalize_field(part))
        return tokens

    def _mentions_real_join(self, instruction: str) -> bool:
        """Return True only when the instruction asks for a real table join.

        Multi-source metrics such as target progress can read actuals and
        targets in separate CTEs without a row-level relation in SchemaGraph.
        Also avoid treating "no relation needed" wording as a join request.
        """
        text = instruction or ""
        if "JOIN" in text.upper():
            return True

        compact = "".join(text.split())
        negative_markers = (
            "无关联",
            "无需关联",
            "无需表关联",
            "无须关联",
            "不关联",
            "单表",
            "無關聯",
            "無需關聯",
        )
        if any(marker in compact for marker in negative_markers):
            return False

        return "关联" in text or "關聯" in text

    def _is_target_progress_metric(self, step_fields: set[str]) -> bool:
        """Target progress metrics combine actual and target aggregates.

        They use both the execution fact table and the monthly target table,
        but do not require a row-level business relation such as tenant_id or
        main_order_id in SchemaGraph.
        """
        return (
            "dm_opt_qy_user_execution_record_all_d.exe_income" in step_fields
            and "dim_channel_month_income_target.target_absolute_value" in step_fields
        )

    def _looks_like_field_reference(self, token: str) -> bool:
        """Only flag tokens that look like technical field references.

        Chinese business labels ("门店", "核销收入") are display names that
        naturally appear in output_target without being in processing_objects.
        Only check tokens that contain dots or underscores — these are actual
        field identifiers that must be grounded.
        """
        return "." in token or "_" in token
