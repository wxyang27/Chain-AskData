from typing import Any

from app.knowledge_indexer.keyword_extractor import KeywordExtractor
from app.knowledge_indexer.reranker import LightweightReranker
from app.knowledge_indexer.types import KnowledgeChunk
from app.schema_index.loader import SchemaIndexBundle


def reciprocal_rank_fusion(
    rankings: list[list[dict[str, Any]]],
    k: int = 60,
) -> list[dict[str, Any]]:
    scores: dict[str, float] = {}
    items: dict[str, dict[str, Any]] = {}

    for ranking in rankings:
        for rank, item in enumerate(ranking, start=1):
            item_id = str(item.get("id") or _match_id(item))
            scores[item_id] = scores.get(item_id, 0.0) + 1.0 / (k + rank)
            items.setdefault(item_id, item.copy())

    fused = []
    for item_id, item in items.items():
        merged = item.copy()
        merged["id"] = item_id
        merged["rrf_score"] = scores[item_id]
        fused.append(merged)

    fused.sort(key=lambda item: -item["rrf_score"])
    return fused


class HybridRetriever:
    """Keyword + vector retrieval over the current unified knowledge assets."""

    def __init__(
        self,
        chunks: list[KnowledgeChunk],
        keyword_extractor: KeywordExtractor | None = None,
        reranker: LightweightReranker | None = None,
        schema_indexes: SchemaIndexBundle | None = None,
    ):
        self.chunks = chunks
        self.keyword_extractor = keyword_extractor or KeywordExtractor()
        self.reranker = reranker or LightweightReranker()
        self.schema_indexes = schema_indexes

    def retrieve(
        self,
        query_text: str,
        vector_matches: list[dict[str, Any]],
        top_k: int,
    ) -> list[dict[str, Any]]:
        keyword_matches = self._keyword_retrieve(query_text, limit=max(top_k * 4, 20))
        schema_index_matches = self._schema_index_retrieve(query_text, limit=max(top_k * 4, 20))
        normalized_vector_matches = [
            self._normalize_vector_match(match)
            for match in vector_matches
        ]
        fused = reciprocal_rank_fusion([keyword_matches, schema_index_matches, normalized_vector_matches])
        candidates = [
            {
                "document": item.get("document", ""),
                "metadata": item.get("metadata", {}) or {},
                "distance": float(item.get("distance", 1.0)) - float(item.get("rrf_score", 0.0)),
            }
            for item in fused
        ]
        return self.reranker.rerank(query_text, candidates, top_k)

    def _keyword_retrieve(self, query_text: str, limit: int) -> list[dict[str, Any]]:
        keywords = self.keyword_extractor.extract(query_text)
        matches = []
        for chunk in self.chunks:
            searchable = chunk.document + "\n" + " ".join(str(value) for value in chunk.metadata.values())
            score = sum(1 for keyword in keywords if keyword and keyword in searchable)
            if score == 0:
                continue
            matches.append(
                {
                    "id": chunk.chunk_id,
                    "document": chunk.document,
                    "metadata": chunk.metadata,
                    "distance": 1.0 / (score + 1),
                    "keyword_score": score,
                }
            )

        matches.sort(key=lambda item: (-item["keyword_score"], item["distance"]))
        return matches[:limit]

    def _schema_index_retrieve(self, query_text: str, limit: int) -> list[dict[str, Any]]:
        if not self.schema_indexes:
            return []

        keywords = self.keyword_extractor.extract(query_text)
        matches: list[dict[str, Any]] = []
        matches.extend(self._schema_field_matches(keywords, limit))
        matches.extend(self._schema_metric_matches(keywords, limit))
        matches.extend(self._schema_table_matches(keywords, limit))
        matches.sort(key=lambda item: (-item["keyword_score"], item["distance"]))
        return matches[:limit]

    def _schema_field_matches(self, keywords: list[str], limit: int) -> list[dict[str, Any]]:
        assert self.schema_indexes is not None
        matches = []
        for row in self.schema_indexes.schema_field_keyword_index:
            score = self._keyword_score(keywords, row)
            if score == 0:
                continue

            field_id = row["field_id"]
            detail = self.schema_indexes.field_detail_by_id.get(field_id, {})
            rerank = self.schema_indexes.field_rerank_by_id.get(field_id, {})
            metadata = {
                **row,
                **detail,
                "asset_type": "field",
                "full_name": self._field_full_name(detail or row),
            }
            matches.append(
                {
                    "id": f"field:{field_id}",
                    "document": rerank.get("rerank_text") or row.get("keyword_text", ""),
                    "metadata": metadata,
                    "distance": 1.0 / (score + 1),
                    "keyword_score": score,
                }
            )
        return matches[:limit]

    def _schema_metric_matches(self, keywords: list[str], limit: int) -> list[dict[str, Any]]:
        assert self.schema_indexes is not None
        matches = []
        for row in self.schema_indexes.metric_keyword_index:
            score = self._keyword_score(keywords, row)
            if score == 0:
                continue

            metric_id = row["metric_id"]
            rerank = self.schema_indexes.metric_rerank_by_id.get(metric_id, {})
            metadata = {
                **row,
                **rerank,
                "asset_type": "metric",
                "metric_id": metric_id,
                "canonical": metric_id,
                "display_name": row.get("metric_name", ""),
            }
            matches.append(
                {
                    "id": f"metric:{metric_id}",
                    "document": rerank.get("rerank_text") or row.get("keyword_text", ""),
                    "metadata": metadata,
                    "distance": 1.0 / (score + 1),
                    "keyword_score": score,
                }
            )
        return matches[:limit]

    def _schema_table_matches(self, keywords: list[str], limit: int) -> list[dict[str, Any]]:
        assert self.schema_indexes is not None
        matches = []
        for row in self.schema_indexes.schema_table_index:
            score = self._keyword_score(keywords, row)
            if score == 0:
                continue

            matches.append(
                {
                    "id": f"table:{row['table_name']}",
                    "document": row.get("table_summary") or row.get("full_name", ""),
                    "metadata": {**row, "asset_type": "table"},
                    "distance": 1.0 / (score + 1),
                    "keyword_score": score,
                }
            )
        return matches[:limit]

    def _keyword_score(self, keywords: list[str], row: dict[str, Any]) -> int:
        searchable = "\n".join(str(value) for value in row.values())
        return sum(1 for keyword in keywords if keyword and keyword in searchable)

    def _field_full_name(self, row: dict[str, Any]) -> str:
        database_name = row.get("database_name") or "soyoung_dw"
        table_name = row.get("table_name", "")
        field_name = row.get("field_name", "")
        if table_name and field_name:
            return f"{database_name}.{table_name}.{field_name}"
        return field_name

    def _normalize_vector_match(self, match: dict[str, Any]) -> dict[str, Any]:
        item = match.copy()
        item["id"] = _match_id(item)
        return item


def _match_id(match: dict[str, Any]) -> str:
    metadata = match.get("metadata", {}) or {}
    if metadata.get("asset_type") == "field":
        return f"field:{metadata.get('table_name')}:{metadata.get('field_name')}"
    if metadata.get("asset_type") == "metric":
        return f"metric:{metadata.get('metric_id') or metadata.get('canonical')}"
    if metadata.get("asset_type") == "table":
        return f"table:{metadata.get('table_name')}"
    if metadata.get("asset_type") == "demo_query":
        return f"demo:{metadata.get('case_id') or metadata.get('template_id')}"
    if metadata.get("asset_type") == "relation":
        return f"relation:{metadata.get('left_table')}:{metadata.get('right_table')}"
    return str(match.get("document", ""))[:120]
