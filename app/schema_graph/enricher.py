"""SchemaGraph field enricher using a template-level dependency matrix.

Keyword-based retrieval can miss essential fields (dp, is_valid, tenant_id)
because they are never semantically matched by query text.  This module
injects required fields from schema indexes so the LLM prompt always
contains the minimum fields needed to produce a valid CoT / SQL.
"""

from typing import Any

from app.schema_graph.graph import SchemaGraph
from app.schema_index.loader import SchemaIndexBundle

_CITY_TERMS = (
    "\u57ce\u5e02",
    "\u5317\u4eac",
    "\u4e0a\u6d77",
    "\u5e7f\u5dde",
    "\u6df1\u5733",
    "\u6b66\u6c49",
    "\u676d\u5dde",
    "\u6210\u90fd",
    "\u91cd\u5e86",
    "\u5929\u6d25",
    "\u5357\u4eac",
    "\u82cf\u5dde",
    "\u897f\u5b89",
    "\u90d1\u5dde",
    "\u957f\u6c99",
    "\u9752\u5c9b",
    "\u5b81\u6ce2",
    "\u5408\u80a5",
    "\u4f5b\u5c71",
    "\u4e1c\u839e",
)
_AREA_TERMS = ("\u5927\u533a", "\u534e\u5317", "\u534e\u4e1c", "\u534e\u5357", "\u534e\u4e2d")
_STORE_TERMS = ("\u95e8\u5e97", "\u673a\u6784", "\u533b\u9662", "\u5404\u5e97", "\u5e97\u94fa")
_CHANNEL_TERMS = ("\u6e20\u9053", "\u79c1\u57df", "\u516c\u57df", "\u8001\u5e26\u65b0")
_NEW_OLD_TERMS = ("\u65b0\u8001\u5ba2", "\u65b0\u5ba2", "\u8001\u5ba2")
_ITEM_TERMS = (
    "\u54c1\u9879",
    "\u9879\u76ee",
    "\u6807\u51c6\u54c1\u9879",
    "\u5947\u8ff9\u80f6\u539f",
    "BBL HERO",
    "\u5947\u8ff9\u7ae5\u989c",
    "\u70ed\u739b\u5409",
)
_FACT_TABLES_WITH_TENANT = (
    "dm_opt_qy_user_execution_record_all_d",
    "dm_opt_qy_order_info_all_d",
)


# ---------------------------------------------------------------------------
# Dependency matrix: template_id -> (table_name, field_name) pairs
#
# Fields are selected by asking "what must a correct SQL for this question
# reference?" and back-tracing through metrics -> fields -> tables -> joins.
# ---------------------------------------------------------------------------

REQUIRED_FIELDS_BY_TEMPLATE: dict[str, list[tuple[str, str]]] = {
    "execution_summary_yesterday": [
        ("dm_opt_qy_user_execution_record_all_d", "dp"),
        ("dm_opt_qy_user_execution_record_all_d", "is_valid"),
        ("dm_opt_qy_user_execution_record_all_d", "executed_date"),
        ("dm_opt_qy_user_execution_record_all_d", "exe_income"),
        ("dm_opt_qy_user_execution_record_all_d", "exe_amount"),
        ("dm_opt_qy_user_execution_record_all_d", "customer_id"),
        ("dm_opt_qy_user_execution_record_all_d", "verify_date_id"),
    ],
    "store_income_top10_30d": [
        ("dm_opt_qy_user_execution_record_all_d", "dp"),
        ("dm_opt_qy_user_execution_record_all_d", "is_valid"),
        ("dm_opt_qy_user_execution_record_all_d", "executed_date"),
        ("dm_opt_qy_user_execution_record_all_d", "exe_income"),
        ("dm_opt_qy_user_execution_record_all_d", "tenant_id"),
        ("dim_qy_tenant_info_all_d", "dp"),
        ("dim_qy_tenant_info_all_d", "tenant_id"),
        ("dim_qy_tenant_info_all_d", "sy_hospital_name"),
    ],
    "private_new_customer_income_this_week": [
        ("dm_opt_qy_user_execution_record_all_d", "dp"),
        ("dm_opt_qy_user_execution_record_all_d", "is_valid"),
        ("dm_opt_qy_user_execution_record_all_d", "executed_date"),
        ("dm_opt_qy_user_execution_record_all_d", "exe_income"),
        ("dm_opt_qy_user_execution_record_all_d", "is_new"),
        ("dm_opt_qy_user_execution_record_all_d", "cx_first_channel"),
    ],
    "channel_execution_30d": [
        ("dm_opt_qy_user_execution_record_all_d", "dp"),
        ("dm_opt_qy_user_execution_record_all_d", "is_valid"),
        ("dm_opt_qy_user_execution_record_all_d", "executed_date"),
        ("dm_opt_qy_user_execution_record_all_d", "exe_income"),
        ("dm_opt_qy_user_execution_record_all_d", "verify_date_id"),
        ("dm_opt_qy_user_execution_record_all_d", "cx_first_channel"),
    ],
    "new_old_customer_execution_30d": [
        ("dm_opt_qy_user_execution_record_all_d", "dp"),
        ("dm_opt_qy_user_execution_record_all_d", "is_valid"),
        ("dm_opt_qy_user_execution_record_all_d", "executed_date"),
        ("dm_opt_qy_user_execution_record_all_d", "exe_income"),
        ("dm_opt_qy_user_execution_record_all_d", "verify_date_id"),
        ("dm_opt_qy_user_execution_record_all_d", "is_new"),
    ],
    "revenue_category_execution_30d": [
        ("dm_opt_qy_user_execution_record_all_d", "dp"),
        ("dm_opt_qy_user_execution_record_all_d", "is_valid"),
        ("dm_opt_qy_user_execution_record_all_d", "executed_date"),
        ("dm_opt_qy_user_execution_record_all_d", "exe_income"),
        ("dm_opt_qy_user_execution_record_all_d", "revenue_category"),
    ],
    # --- remaining execution_record templates ---
    "standard_item_income_top20_30d": [
        ("dm_opt_qy_user_execution_record_all_d", "dp"),
        ("dm_opt_qy_user_execution_record_all_d", "is_valid"),
        ("dm_opt_qy_user_execution_record_all_d", "executed_date"),
        ("dm_opt_qy_user_execution_record_all_d", "exe_income"),
        ("dm_opt_qy_user_execution_record_all_d", "standard_name"),
    ],
    "standard_item_penetration_90d": [
        ("dm_opt_qy_user_execution_record_all_d", "dp"),
        ("dm_opt_qy_user_execution_record_all_d", "is_valid"),
        ("dm_opt_qy_user_execution_record_all_d", "executed_date"),
        ("dm_opt_qy_user_execution_record_all_d", "exe_income"),
        ("dm_opt_qy_user_execution_record_all_d", "standard_name"),
        ("dm_opt_qy_user_execution_record_all_d", "customer_id"),
    ],
    "zero_income_orders_30d": [
        ("dm_opt_qy_user_execution_record_all_d", "dp"),
        ("dm_opt_qy_user_execution_record_all_d", "is_valid"),
        ("dm_opt_qy_user_execution_record_all_d", "executed_date"),
        ("dm_opt_qy_user_execution_record_all_d", "exe_income"),
        ("dm_opt_qy_user_execution_record_all_d", "customer_id"),
        ("dm_opt_qy_user_execution_record_all_d", "main_order_id"),
    ],
    "upgrade_execution_30d": [
        ("dm_opt_qy_user_execution_record_all_d", "dp"),
        ("dm_opt_qy_user_execution_record_all_d", "is_valid"),
        ("dm_opt_qy_user_execution_record_all_d", "executed_date"),
        ("dm_opt_qy_user_execution_record_all_d", "exe_income"),
        ("dm_opt_qy_user_execution_record_all_d", "customer_id"),
        ("dm_opt_qy_user_execution_record_all_d", "verify_date_id"),
        ("dm_opt_qy_user_execution_record_all_d", "is_up"),
    ],
    # --- order_info templates ---
    "unverified_amount_store_top10": [
        ("dm_opt_qy_order_info_all_d", "dp"),
        ("dm_opt_qy_order_info_all_d", "tenant_id"),
        ("dm_opt_qy_order_info_all_d", "left_gmv"),
        ("dm_opt_qy_order_info_all_d", "left_num"),
        ("dim_qy_tenant_info_all_d", "dp"),
        ("dim_qy_tenant_info_all_d", "tenant_id"),
        ("dim_qy_tenant_info_all_d", "sy_hospital_name"),
    ],
    "new_customer_payment_30d": [
        ("dm_opt_qy_order_info_all_d", "dp"),
        ("dm_opt_qy_order_info_all_d", "pay_date"),
        ("dm_opt_qy_order_info_all_d", "pay_gmv"),
        ("dm_opt_qy_order_info_all_d", "uid"),
        ("dm_opt_qy_order_info_all_d", "is_pay_new"),
        ("dm_opt_qy_order_info_all_d", "is_paydate_cash"),
    ],
    "pay_to_verify_rate_30d": [
        ("dm_opt_qy_order_info_all_d", "dp"),
        ("dm_opt_qy_order_info_all_d", "pay_date"),
        ("dm_opt_qy_order_info_all_d", "pay_gmv"),
        ("dm_opt_qy_order_info_all_d", "uid"),
        ("dm_opt_qy_user_execution_record_all_d", "dp"),
        ("dm_opt_qy_user_execution_record_all_d", "is_valid"),
        ("dm_opt_qy_user_execution_record_all_d", "executed_date"),
        ("dm_opt_qy_user_execution_record_all_d", "exe_income"),
        ("dm_opt_qy_user_execution_record_all_d", "main_order_id"),
    ],
}

# ---------------------------------------------------------------------------
# Template-level relation requirements
#   (source_table, source_field, target_table, target_field)
# ---------------------------------------------------------------------------

REQUIRED_RELATIONS_BY_TEMPLATE: dict[str, list[tuple[str, str, str, str]]] = {
    "store_income_top10_30d": [
        ("dm_opt_qy_user_execution_record_all_d", "tenant_id",
         "dim_qy_tenant_info_all_d", "tenant_id"),
    ],
    "unverified_amount_store_top10": [
        ("dm_opt_qy_order_info_all_d", "tenant_id",
         "dim_qy_tenant_info_all_d", "tenant_id"),
    ],
    "pay_to_verify_rate_30d": [
        ("dm_opt_qy_order_info_all_d", "main_order_id",
         "dm_opt_qy_user_execution_record_all_d", "main_order_id"),
    ],
}


# Synthetic field descriptions for entries not present in field_detail_index
_SYNTHETIC_FIELDS: dict[str, dict[str, Any]] = {
    "dm_opt_qy_user_execution_record_all_d.dp": {
        "field_id": "dm_opt_qy_user_execution_record_all_d.dp",
        "database_name": "soyoung_dw",
        "table_name": "dm_opt_qy_user_execution_record_all_d",
        "field_name": "dp",
        "field_type": "date",
        "field_description": "分区日期字段，用于数据分区和日期范围筛选",
        "business_name": "分区日期",
        "caliber": "取数时默认使用 DATE_SUB(CURRENT_DATE(),1)",
        "sample_values": ["DATE_SUB(CURRENT_DATE(),1)"],
        "value_range": [],
        "filters": [],
        "risk_notes": [],
        "is_join_key": False,
        "is_metric_field": False,
        "is_dimension_field": False,
    },
    "dm_opt_qy_user_execution_record_all_d.tenant_id": {
        "field_id": "dm_opt_qy_user_execution_record_all_d.tenant_id",
        "database_name": "soyoung_dw",
        "table_name": "dm_opt_qy_user_execution_record_all_d",
        "field_name": "tenant_id",
        "field_type": "bigint",
        "field_description": "门店唯一标识，用于关联门店维度表 dim_qy_tenant_info_all_d",
        "business_name": "门店ID",
        "caliber": "关联键，通过 tenant_id 关联 dim_qy_tenant_info_all_d 获取门店名称",
        "sample_values": [],
        "value_range": [],
        "filters": [],
        "risk_notes": [],
        "is_join_key": True,
        "is_metric_field": False,
        "is_dimension_field": False,
    },
    "dim_qy_tenant_info_all_d.dp": {
        "field_id": "dim_qy_tenant_info_all_d.dp",
        "database_name": "soyoung_dw",
        "table_name": "dim_qy_tenant_info_all_d",
        "field_name": "dp",
        "field_type": "date",
        "field_description": "分区日期字段，用于数据分区和日期范围筛选",
        "business_name": "分区日期",
        "caliber": "取数时默认使用 DATE_SUB(CURRENT_DATE(),1)",
        "sample_values": ["DATE_SUB(CURRENT_DATE(),1)"],
        "value_range": [],
        "filters": [],
        "risk_notes": [],
        "is_join_key": False,
        "is_metric_field": False,
        "is_dimension_field": False,
    },
    "dm_opt_qy_order_info_all_d.dp": {
        "field_id": "dm_opt_qy_order_info_all_d.dp",
        "database_name": "soyoung_dw",
        "table_name": "dm_opt_qy_order_info_all_d",
        "field_name": "dp",
        "field_type": "date",
        "field_description": "分区日期字段，用于数据分区和日期范围筛选",
        "business_name": "分区日期",
        "caliber": "取数时默认使用 DATE_SUB(CURRENT_DATE(),1)",
        "sample_values": ["DATE_SUB(CURRENT_DATE(),1)"],
        "value_range": [],
        "filters": [],
        "risk_notes": [],
        "is_join_key": False,
        "is_metric_field": False,
        "is_dimension_field": False,
    },
    "dm_opt_qy_order_info_all_d.tenant_id": {
        "field_id": "dm_opt_qy_order_info_all_d.tenant_id",
        "database_name": "soyoung_dw",
        "table_name": "dm_opt_qy_order_info_all_d",
        "field_name": "tenant_id",
        "field_type": "bigint",
        "field_description": "门店唯一标识，用于关联门店维度表 dim_qy_tenant_info_all_d",
        "business_name": "门店ID",
        "caliber": "关联键，通过 tenant_id 关联 dim_qy_tenant_info_all_d 获取门店名称",
        "sample_values": [],
        "value_range": [],
        "filters": [],
        "risk_notes": [],
        "is_join_key": True,
        "is_metric_field": False,
        "is_dimension_field": False,
    },
}


def _compute_full_name(field_entry: dict[str, Any]) -> str:
    database_name = field_entry.get("database_name") or "soyoung_dw"
    table_name = field_entry.get("table_name", "")
    field_name = field_entry.get("field_name", "")
    if table_name and field_name:
        return f"{database_name}.{table_name}.{field_name}"
    return field_name


class SchemaGraphEnricher:
    """Post-process a SchemaGraph to inject required fields from schema indexes."""

    def __init__(self, schema_indexes: SchemaIndexBundle):
        self._indexes = schema_indexes

    def enrich(
        self,
        schema_graph: SchemaGraph,
        template_id: str,
    ) -> SchemaGraph:
        required = list(REQUIRED_FIELDS_BY_TEMPLATE.get(template_id, []))
        existing_table_names = {
            t.get("table_name") or ""
            for t in schema_graph.tables
        }
        required.extend(
            self._query_dimension_fields(
                query=schema_graph.query,
                seed_required=required,
                existing_table_names=existing_table_names,
            )
        )
        if not required:
            return schema_graph

        existing_field_ids = {
            self._field_id(f) for f in schema_graph.fields
        }

        supplemented: list[str] = []
        new_fields: list[dict[str, Any]] = []

        for table_name, field_name in required:
            fid = f"{table_name}.{field_name}"
            if fid in existing_field_ids:
                continue

            entry = self._lookup_field(table_name, field_name)
            if entry is None:
                continue

            entry.setdefault("asset_type", "field")
            if "full_name" not in entry:
                entry["full_name"] = _compute_full_name(entry)
            new_fields.append(entry)
            existing_field_ids.add(fid)
            supplemented.append(fid)

            if table_name not in existing_table_names:
                existing_table_names.add(table_name)

        merged_fields = list(schema_graph.fields) + new_fields

        # Ensure new tables have entries
        merged_tables = list(schema_graph.tables)
        for table_name in existing_table_names:
            if table_name not in {t.get("table_name", "") for t in merged_tables}:
                table_entry = self._indexes.table_by_name.get(table_name)
                if table_entry:
                    merged_tables.append({**table_entry, "asset_type": "table",
                                          "derived_from": "enricher"})

        # Supplement relations: template-required + index lookup for new table pairs
        merged_relations = list(schema_graph.relations)
        merged_relations = self._supplement_relations(
            merged_relations, merged_tables, template_id,
        )

        return SchemaGraph(
            query=schema_graph.query,
            tables=merged_tables,
            fields=merged_fields,
            metrics=list(schema_graph.metrics),
            relations=merged_relations,
            missing_evidence=list(schema_graph.missing_evidence),
            schema_graph_text=schema_graph.schema_graph_text,
            supplemented_fields=supplemented,
        )

    # ------------------------------------------------------------------
    # internal helpers
    # ------------------------------------------------------------------

    def _query_dimension_fields(
        self,
        *,
        query: str,
        seed_required: list[tuple[str, str]],
        existing_table_names: set[str],
    ) -> list[tuple[str, str]]:
        """Add tenant dimension dependencies implied by the user's wording."""
        query = query or ""
        fields: list[tuple[str, str]] = []
        fact_tables = self._fact_tables_for_dimension(seed_required, existing_table_names)
        if not fact_tables:
            return fields

        needs_city = any(term in query for term in _CITY_TERMS)
        needs_area = any(term in query for term in _AREA_TERMS)
        needs_store = any(term in query for term in _STORE_TERMS)
        needs_channel = any(term in query for term in _CHANNEL_TERMS)
        needs_new_old = any(term in query for term in _NEW_OLD_TERMS)
        needs_item = any(term in query for term in _ITEM_TERMS)
        if not (needs_city or needs_area or needs_store or needs_channel or needs_new_old or needs_item):
            return fields

        if needs_city or needs_area or needs_store:
            for table_name in fact_tables:
                fields.append((table_name, "tenant_id"))
            fields.extend([
                ("dim_qy_tenant_info_all_d", "dp"),
                ("dim_qy_tenant_info_all_d", "tenant_id"),
            ])
            if needs_city:
                fields.append(("dim_qy_tenant_info_all_d", "city_name"))
            if needs_area:
                fields.append(("dim_qy_tenant_info_all_d", "area_name"))
            if needs_store:
                fields.append(("dim_qy_tenant_info_all_d", "sy_hospital_name"))

        if "dm_opt_qy_user_execution_record_all_d" in fact_tables:
            if needs_channel:
                fields.append(("dm_opt_qy_user_execution_record_all_d", "cx_first_channel"))
            if needs_new_old:
                fields.append(("dm_opt_qy_user_execution_record_all_d", "is_new"))
            if needs_item:
                fields.append(("dm_opt_qy_user_execution_record_all_d", "standard_name"))

        if "dm_opt_qy_order_info_all_d" in fact_tables:
            if needs_new_old:
                fields.append(("dm_opt_qy_order_info_all_d", "is_pay_new"))
            if needs_item:
                fields.append(("dm_opt_qy_order_info_all_d", "standard_name"))
        return fields

    def _fact_tables_for_dimension(
        self,
        seed_required: list[tuple[str, str]],
        existing_table_names: set[str],
    ) -> list[str]:
        available = set(existing_table_names)
        available.update(table for table, _ in seed_required)
        return [table for table in _FACT_TABLES_WITH_TENANT if table in available]

    def _supplement_relations(
        self,
        relations: list[dict[str, Any]],
        tables: list[dict[str, Any]],
        template_id: str,
    ) -> list[dict[str, Any]]:
        table_names = {
            t.get("table_name") or ""
            for t in tables
        }

        # Existing relation keys for dedup
        existing_keys = {
            (r.get("source_table"), r.get("source_field"),
             r.get("target_table"), r.get("target_field"))
            for r in relations
        }

        # 1. Index lookup: find relations where both tables are present
        for rel in self._indexes.schema_relation_index:
            src = rel.get("source_table", "")
            tgt = rel.get("target_table", "")
            if src in table_names and tgt in table_names:
                key = (src, rel.get("source_field"), tgt, rel.get("target_field"))
                if key not in existing_keys:
                    relations.append(dict(rel))
                    existing_keys.add(key)

        # 2. Template-required relations
        required_rels = REQUIRED_RELATIONS_BY_TEMPLATE.get(template_id, [])
        for src_t, src_f, tgt_t, tgt_f in required_rels:
            if src_t in table_names and tgt_t in table_names:
                key = (src_t, src_f, tgt_t, tgt_f)
                if key not in existing_keys:
                    relations.append({
                        "source_table": src_t,
                        "source_field": src_f,
                        "target_table": tgt_t,
                        "target_field": tgt_f,
                        "relation_type": "LEFT JOIN",
                        "relation_description": f"模板级补全：{src_t}.{src_f} ↔ {tgt_t}.{tgt_f}",
                    })
                    existing_keys.add(key)

        return relations

    def _lookup_field(
        self,
        table_name: str,
        field_name: str,
    ) -> dict[str, Any] | None:
        field_id = f"{table_name}.{field_name}"

        # 1. Try field_detail_by_id
        detail = self._indexes.field_detail_by_id.get(field_id)
        if detail:
            return dict(detail)

        # 2. Try synthetic
        synthetic = _SYNTHETIC_FIELDS.get(field_id)
        if synthetic:
            return dict(synthetic)

        # 3. Try building from keyword index
        for row in self._indexes.schema_field_keyword_index:
            if row.get("table_name") == table_name and row.get("field_name") == field_name:
                entry = dict(row)
                entry["asset_type"] = "field"
                return entry

        return None

    @staticmethod
    def _field_id(field: dict[str, Any]) -> str:
        table = field.get("table_name") or ""
        name = field.get("field_name") or ""
        return f"{table}.{name}" if table and name else field.get("field_id") or ""
