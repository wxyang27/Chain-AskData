import json
from pathlib import Path
from typing import Any

from app.knowledge_indexer.types import KnowledgeChunk


GENERATED_ASSET_FILES = {
    "metrics_full.json": "metric",
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

    chunks: list[KnowledgeChunk] = []
    for filename, asset_type in GENERATED_ASSET_FILES.items():
        path = generated_dir / filename
        if not path.exists():
            continue
        records = json.loads(path.read_text(encoding="utf-8"))
        for record in records:
            chunk = _record_to_chunk(asset_type, record)
            if chunk:
                chunks.append(chunk)

    return chunks


def _record_to_chunk(asset_type: str, record: dict[str, Any]) -> KnowledgeChunk | None:
    if asset_type == "metric":
        return _metric_chunk(record)
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
