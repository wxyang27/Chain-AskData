from app.assets.loader import load_yaml_asset
from app.knowledge_importer.chunker import load_generated_knowledge_chunks
from app.knowledge_indexer.types import KnowledgeChunk


def load_knowledge_chunks(
    include_generated: bool = False,
    generated_dir: str = "knowledge/generated",
) -> list[KnowledgeChunk]:
    """加载本地知识资产并切成 ChromaDB 文档块。"""

    chunks: list[KnowledgeChunk] = []
    chunks.extend(_load_metric_chunks())
    chunks.extend(_load_field_chunks())
    chunks.extend(_load_table_chunks())
    chunks.extend(_load_relation_chunks())
    chunks.extend(_load_demo_query_chunks())
    if include_generated:
        chunks.extend(load_generated_knowledge_chunks(generated_dir))
    return chunks


def _load_metric_chunks() -> list[KnowledgeChunk]:
    asset = load_yaml_asset("knowledge/metrics/core_metrics.yaml")
    chunks = []

    for metric in asset["metrics"]:
        notes = "；".join(metric.get("notes", []))
        filters = "；".join(metric.get("required_filters", []))
        document = (
            f"指标：{metric['display_name']}\n"
            f"指标编码：{metric['canonical']}\n"
            f"计算公式：{metric['formula']}\n"
            f"来源表：{metric['source_table']}\n"
            f"业务日期字段：{metric['date_field']}\n"
            f"必备过滤：{filters}\n"
            f"口径说明：{notes}"
        )
        chunks.append(
            KnowledgeChunk(
                chunk_id=f"metric:{metric['canonical']}",
                document=document,
                metadata={
                    "asset_type": "metric",
                    "canonical": metric["canonical"],
                    "display_name": metric["display_name"],
                    "source_table": metric["source_table"],
                },
            )
        )

    return chunks


def _load_table_chunks() -> list[KnowledgeChunk]:
    asset = load_yaml_asset("knowledge/tables/core_tables.yaml")
    chunks = []

    for table in asset["tables"]:
        key_fields = "；".join(table.get("key_fields", []))
        date_fields = "；".join(table.get("date_fields", []))
        caliber_rules = "；".join(table.get("caliber_rules", []))
        document = (
            f"表：{table['full_name']}\n"
            f"分层：{table['layer']}\n"
            f"主题：{table['theme']}\n"
            f"粒度：{table['grain']}\n"
            f"分区字段：{table['required_partition']}\n"
            f"日期字段：{date_fields}\n"
            f"关键字段：{key_fields}\n"
            f"口径规则：{caliber_rules}"
        )
        chunks.append(
            KnowledgeChunk(
                chunk_id=f"table:{table['name']}",
                document=document,
                metadata={
                    "asset_type": "table",
                    "table_name": table["name"],
                    "full_name": table["full_name"],
                    "theme": table["theme"],
                },
            )
        )

    return chunks


def _load_field_chunks() -> list[KnowledgeChunk]:
    asset = load_yaml_asset("knowledge/schema/core_fields.yaml")
    chunks = []

    for field in asset["fields"]:
        used_by_metrics = "；".join(field.get("used_by_metrics", []))
        filters = "；".join(field.get("filters", []))
        risk_notes = "；".join(field.get("risk_notes", []))
        document = (
            f"字段：{field['field_name']}\n"
            f"业务含义：{field['business_name']}\n"
            f"来源表：{field['full_table_name']}\n"
            f"字段类型：{field['field_type']}\n"
            f"统一名称：{field['canonical_name']}\n"
            f"相关指标：{used_by_metrics}\n"
            f"口径说明：{field['caliber']}\n"
            f"必备过滤：{filters}\n"
            f"易错提醒：{risk_notes}"
        )
        chunks.append(
            KnowledgeChunk(
                chunk_id=f"field:{field['table_name']}:{field['field_name']}",
                document=document,
                metadata={
                    "asset_type": "field",
                    "field_name": field["field_name"],
                    "business_name": field["business_name"],
                    "table_name": field["table_name"],
                    "full_table_name": field["full_table_name"],
                    "full_name": f"{field['full_table_name']}.{field['field_name']}",
                    "field_type": field["field_type"],
                    "canonical_name": field["canonical_name"],
                    "used_by_metrics": used_by_metrics,
                },
            )
        )

    return chunks


def _load_relation_chunks() -> list[KnowledgeChunk]:
    asset = load_yaml_asset("knowledge/relations/table_relations.yaml")
    chunks = []

    for index, relation in enumerate(asset["relations"], start=1):
        join_keys = "；".join(relation.get("join_keys", []))
        document = (
            f"表关系：{relation['left_table']} {relation['join_type']} {relation['right_table']}\n"
            f"关联键：{join_keys}\n"
            f"关联条件：{relation['condition']}\n"
            f"使用场景：{relation['usage']}"
        )
        chunks.append(
            KnowledgeChunk(
                chunk_id=f"relation:{index}",
                document=document,
                metadata={
                    "asset_type": "relation",
                    "left_table": relation["left_table"],
                    "right_table": relation["right_table"],
                    "usage": relation["usage"],
                },
            )
        )

    return chunks


def _load_demo_query_chunks() -> list[KnowledgeChunk]:
    demo_cases = load_yaml_asset("knowledge/examples/demo_queries.json")
    chunks = []

    for demo_case in demo_cases:
        metrics = "；".join(demo_case.get("metrics", []))
        source_tables = "；".join(demo_case.get("source_tables", []))
        risk_flags = "；".join(demo_case.get("risk_flags", []))
        document = (
            f"样例问题：{demo_case['question']}\n"
            f"样例编号：{demo_case['case_id']}\n"
            f"SQL模板：{demo_case['template_id']}\n"
            f"业务域：{demo_case['business_domain']}\n"
            f"相关指标：{metrics}\n"
            f"来源表：{source_tables}\n"
            f"风险提示：{risk_flags}"
        )
        chunks.append(
            KnowledgeChunk(
                chunk_id=f"demo:{demo_case['case_id']}",
                document=document,
                metadata={
                    "asset_type": "demo_query",
                    "case_id": demo_case["case_id"],
                    "template_id": demo_case["template_id"],
                    "business_domain": demo_case["business_domain"],
                },
            )
        )

    return chunks
