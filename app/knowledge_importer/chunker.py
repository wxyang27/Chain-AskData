import json
from pathlib import Path
from typing import Any

from app.knowledge_indexer.types import KnowledgeChunk


GENERATED_ASSET_FILES = {
    "dimensions.json": "dimension",
    "tables.json": "table",
}

LEGACY_GENERATED_ASSET_FILES = {
    "user_profile_fields.json": "user_profile_field",
    "dimensions.json": "dimension",
    "data_sources.json": "data_source",
    "dashboard_metrics.json": "dashboard_metric",
    "tables_full.json": "table",
    "business_playbooks.json": "business_playbook",
}


def load_generated_knowledge_chunks(
    generated_dir: Path | str = Path("knowledge/generated"),
) -> list[KnowledgeChunk]:
    generated_dir = Path(generated_dir)
    if not generated_dir.exists():
        return []

    assets_dir = generated_dir / "assets"
    if assets_dir.exists():
        return _load_consolidated_asset_chunks(assets_dir)

    return _load_legacy_asset_chunks(generated_dir)


def _load_consolidated_asset_chunks(assets_dir: Path) -> list[KnowledgeChunk]:
    chunks: list[KnowledgeChunk] = []
    chunks.extend(_load_preferred_asset_file(assets_dir, "metrics.json", "", "metric"))
    chunks.extend(_load_preferred_asset_file(assets_dir, "fields.json", "", "schema_field"))
    for filename, asset_type in GENERATED_ASSET_FILES.items():
        path = assets_dir / filename
        if not path.exists():
            continue
        records = json.loads(path.read_text(encoding="utf-8"))
        for record in records:
            chunk = _record_to_chunk(asset_type, record)
            if chunk:
                chunks.append(chunk)
    chunks.extend(_load_business_asset_chunks(assets_dir / "business_assets.json"))

    return chunks


def _load_legacy_asset_chunks(generated_dir: Path) -> list[KnowledgeChunk]:
    chunks: list[KnowledgeChunk] = []
    chunks.extend(_load_preferred_asset_file(generated_dir, "metrics_merged.json", "metrics_full.json", "metric"))
    chunks.extend(_load_preferred_asset_file(generated_dir, "fields_merged.json", "", "schema_field"))
    for filename, asset_type in LEGACY_GENERATED_ASSET_FILES.items():
        path = generated_dir / filename
        if not path.exists():
            continue
        records = json.loads(path.read_text(encoding="utf-8"))
        for record in records:
            chunk = _record_to_chunk(asset_type, record)
            if chunk:
                chunks.append(chunk)

    return chunks


def _load_business_asset_chunks(path: Path) -> list[KnowledgeChunk]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    chunks: list[KnowledgeChunk] = []
    for record in payload.get("data_sources", []):
        if chunk := _record_to_chunk("data_source", record):
            chunks.append(chunk)
    for record in payload.get("dashboard_metrics", []):
        if chunk := _record_to_chunk("dashboard_metric", record):
            chunks.append(chunk)
    for record in payload.get("business_playbooks", []):
        if chunk := _record_to_chunk("business_playbook", record):
            chunks.append(chunk)
    for record in payload.get("user_profile_fields", []):
        if chunk := _record_to_chunk("user_profile_field", record):
            chunks.append(chunk)
    return chunks


def _load_preferred_asset_file(
    generated_dir: Path,
    preferred_filename: str,
    fallback_filename: str,
    asset_type: str,
) -> list[KnowledgeChunk]:
    path = generated_dir / preferred_filename
    if not path.exists() and fallback_filename:
        path = generated_dir / fallback_filename
    if not path.exists():
        return []

    records = json.loads(path.read_text(encoding="utf-8"))
    return [
        chunk
        for record in records
        if (chunk := _record_to_chunk(asset_type, record))
    ]


def _record_to_chunk(asset_type: str, record: dict[str, Any]) -> KnowledgeChunk | None:
    if asset_type == "metric":
        return _metric_chunk(record)
    if asset_type == "schema_field":
        return _schema_field_chunk(record)
    if asset_type == "user_profile_field":
        return _field_chunk(record)
    if asset_type == "dimension":
        return _generic_chunk(asset_type, record, record["dimension_id"], _dimension_document(record))
    if asset_type == "data_source":
        return _generic_chunk(asset_type, record, record["source_id"], _data_source_document(record))
    if asset_type == "dashboard_metric":
        return _generic_chunk(asset_type, record, record["sequence"], _dashboard_document(record))
    if asset_type == "table":
        return _table_chunk(record)
    if asset_type == "business_playbook":
        return _generic_chunk(asset_type, record, record["playbook_id"], _playbook_document(record))
    return None


def _metric_chunk(record: dict[str, Any]) -> KnowledgeChunk:
    source_tables = _join(record.get("source_tables", []))
    dashboard_names = _join(record.get("dashboard_names", []))
    document = "\n".join(
        [
            f"指标：{record['name']}",
            f"指标编码：{record['metric_id']}",
            f"指标类型：{record['metric_type']}",
            f"业务域：{record.get('business_domain', '')}",
            f"定义：{record.get('definition', '')}",
            f"计算逻辑：{record.get('formula', '')}",
            f"来源表：{source_tables}",
            f"看板：{dashboard_names}",
            f"SQL：{record.get('sql', '')}",
            f"备注：{record.get('notes', '')}",
            _source_trace(record),
        ]
    )
    return KnowledgeChunk(
        chunk_id=f"generated_metric:{record['metric_id']}",
        document=document,
        metadata=_metadata(
            {
                "asset_type": "metric",
                "canonical": record["metric_id"],
                "display_name": record["name"],
                "metric_type": record["metric_type"],
                "source_table": _first(record.get("source_tables", [])),
                "source_file": record.get("source_file", ""),
                "source_sheet": record.get("source_sheet", ""),
                "review_status": record.get("review_status", ""),
                "source_kind": record.get("source_kind", ""),
            }
        ),
    )


def _schema_field_chunk(record: dict[str, Any]) -> KnowledgeChunk:
    document = "\n".join(
        [
            f"字段：{record['field_name']}",
            f"业务含义：{record.get('business_name', '')}",
            f"来源表：{record.get('full_table_name', '')}",
            f"字段类型：{record.get('field_type', '')}",
            f"字段说明：{record.get('description', '')}",
            f"相关指标：{_join(record.get('used_by_metrics', []))}",
            f"口径说明：{record.get('caliber', '')}",
            f"样例值：{_join(record.get('sample_values', []))}",
            f"枚举值：{_join(record.get('enum_values', []))}",
            f"必备过滤：{_join(record.get('filters', []))}",
            f"易错提醒：{_join(record.get('risk_notes', []))}",
            _source_trace(record),
        ]
    )
    return KnowledgeChunk(
        chunk_id=f"generated_schema_field:{record['table_name']}:{record['field_name']}",
        document=document,
        metadata=_metadata(
            {
                "asset_type": "field",
                "field_name": record["field_name"],
                "business_name": record.get("business_name", ""),
                "table_name": record["table_name"],
                "full_table_name": record.get("full_table_name", ""),
                "full_name": f"{record.get('full_table_name', '')}.{record['field_name']}",
                "field_type": record.get("field_type", ""),
                "canonical_name": record.get("field_name", ""),
                "used_by_metrics": record.get("used_by_metrics", []),
                "is_join_key": record.get("is_join_key", False),
                "is_metric_field": record.get("is_metric_field", False),
                "is_dimension_field": record.get("is_dimension_field", False),
                "review_status": record.get("review_status", ""),
                "source_kind": record.get("source_kind", ""),
                "source_file": record.get("source_file", ""),
            }
        ),
    )


def _field_chunk(record: dict[str, Any]) -> KnowledgeChunk:
    source_tables = _join(record.get("source_tables", []))
    document = "\n".join(
        [
            f"用户画像字段：{record['name']}",
            f"字段编码：{record['field_id']}",
            f"业务板块：{record.get('business_area', '')}",
            f"分类：{record.get('category', '')}",
            f"数据粒度：{record.get('grain', '')}",
            f"定义：{record.get('definition', '')}",
            f"来源表：{source_tables}",
            f"SQL：{record.get('sql', '')}",
            f"备注：{record.get('notes', '')}",
            _source_trace(record),
        ]
    )
    return KnowledgeChunk(
        chunk_id=f"generated_field:{record['field_id']}",
        document=document,
        metadata=_metadata(
            {
                "asset_type": "user_profile_field",
                "field_name": record["name"],
                "business_name": record["name"],
                "table_name": _first(record.get("source_tables", [])),
                "full_table_name": _first(record.get("source_tables", [])),
                "full_name": f"{_first(record.get('source_tables', []))}.{record['name']}",
                "field_type": record.get("data_type", ""),
                "canonical_name": record["field_id"],
                "source_file": record.get("source_file", ""),
                "source_sheet": record.get("source_sheet", ""),
            }
        ),
    )


def _table_chunk(record: dict[str, Any]) -> KnowledgeChunk:
    document = "\n".join(
        [
            f"表：{record['full_name']}",
            f"表名：{record['table_name']}",
            f"分层：{record.get('layer', '')}",
            f"主题：{record.get('theme', '')}",
            f"粒度：{record.get('grain', '')}",
            f"分区字段：{record.get('partition_field', '')}",
            f"主要字段：{_join(record.get('main_fields', []))}",
            f"业务说明：{record.get('business_description', '')}",
            _source_trace(record),
        ]
    )
    return KnowledgeChunk(
        chunk_id=f"generated_table:{record['table_name']}",
        document=document,
        metadata=_metadata(
            {
                "asset_type": "table",
                "table_name": record["table_name"],
                "full_name": record["full_name"],
                "theme": record.get("theme", ""),
                "layer": record.get("layer", ""),
                "source_file": record.get("source_file", ""),
            }
        ),
    )


def _generic_chunk(
    asset_type: str,
    record: dict[str, Any],
    stable_id: str,
    document: str,
) -> KnowledgeChunk:
    return KnowledgeChunk(
        chunk_id=f"generated_{asset_type}:{stable_id}",
        document=document,
        metadata=_metadata(
            {
                "asset_type": asset_type,
                "stable_id": stable_id,
                "display_name": record.get("name", record.get("title", "")),
                "source_file": record.get("source_file", ""),
                "source_sheet": record.get("source_sheet", ""),
            }
        ),
    )


def _dimension_document(record: dict[str, Any]) -> str:
    return "\n".join(
        [
            f"维度：{record['name']}",
            f"维度编码：{record['dimension_id']}",
            f"英文名：{record.get('english_name', '')}",
            f"说明：{record.get('description', '')}",
            f"取值范围：{record.get('value_range', '')}",
            f"对应字段：{_join(record.get('fields', []))}",
            f"所属数据源：{_join(record.get('source_tables', []))}",
            f"影响指标：{record.get('affected_metrics', '')}",
            _source_trace(record),
        ]
    )


def _data_source_document(record: dict[str, Any]) -> str:
    return "\n".join(
        [
            f"数据源表：{record.get('database', '')}.{record['table_name']}",
            f"数据源编码：{record['source_id']}",
            f"简称：{record.get('alias', '')}",
            f"业务说明：{record.get('business_description', '')}",
            f"主要字段：{_join(record.get('main_fields', []))}",
            f"更新频率：{record.get('refresh_frequency', '')}",
            f"分区字段：{record.get('partition_field', '')}",
            f"备注：{record.get('notes', '')}",
            _source_trace(record),
        ]
    )


def _dashboard_document(record: dict[str, Any]) -> str:
    return "\n".join(
        [
            f"看板指标：{record['name']}",
            f"序号：{record['sequence']}",
            f"看板模块：{record.get('module', '')}",
            f"所属看板：{record.get('dashboard', '')}",
            f"定义：{record.get('definition', '')}",
            f"负责人：{record.get('owner', '')}",
            f"匹配指标ID：{record.get('matched_metric_id', '')}",
            _source_trace(record),
        ]
    )


def _playbook_document(record: dict[str, Any]) -> str:
    return "\n".join(
        [
            f"业务分析方法：{record['title']}",
            f"类型：{record.get('content_type', '')}",
            f"内容：{record.get('content', '')}",
            _source_trace(record),
        ]
    )


def _metadata(values: dict[str, Any]) -> dict[str, str]:
    return {key: _stringify(value) for key, value in values.items()}


def _source_trace(record: dict[str, Any]) -> str:
    source_sheet = record.get("source_sheet", "")
    source_row = record.get("source_row", record.get("source_index", ""))
    return f"来源：{record.get('source_file', '')} {source_sheet} {source_row}".strip()


def _stringify(value: Any) -> str:
    if isinstance(value, list):
        return _join(value)
    if value is None:
        return ""
    return str(value)


def _join(value: Any) -> str:
    if isinstance(value, list):
        return "；".join(str(item) for item in value if item)
    return _stringify(value)


def _first(value: Any) -> str:
    if isinstance(value, list):
        return str(value[0]) if value else ""
    return _stringify(value)
