from typing import Any

from app.knowledge_indexer.keyword_extractor import KeywordExtractor
from app.knowledge_indexer.reranker import LightweightReranker
from app.knowledge_indexer.types import KnowledgeChunk


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
    ):
        self.chunks = chunks
        self.keyword_extractor = keyword_extractor or KeywordExtractor()
        self.reranker = reranker or LightweightReranker()

    def retrieve(
        self,
        query_text: str,
        vector_matches: list[dict[str, Any]],
        top_k: int,
    ) -> list[dict[str, Any]]:
        keyword_matches = self._keyword_retrieve(query_text, limit=max(top_k * 4, 20))
        normalized_vector_matches = [
            self._normalize_vector_match(match)
            for match in vector_matches
        ]
        fused = reciprocal_rank_fusion([keyword_matches, normalized_vector_matches])
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

    def _normalize_vector_match(self, match: dict[str, Any]) -> dict[str, Any]:
        item = match.copy()
        item["id"] = _match_id(item)
        return item


def _match_id(match: dict[str, Any]) -> str:
    metadata = match.get("metadata", {}) or {}
    if metadata.get("asset_type") == "field":
        return f"field:{metadata.get('table_name')}:{metadata.get('field_name')}"
    if metadata.get("asset_type") == "metric":
        return f"metric:{metadata.get('canonical')}"
    if metadata.get("asset_type") == "table":
        return f"table:{metadata.get('table_name')}"
    if metadata.get("asset_type") == "demo_query":
        return f"demo:{metadata.get('case_id') or metadata.get('template_id')}"
    if metadata.get("asset_type") == "relation":
        return f"relation:{metadata.get('left_table')}:{metadata.get('right_table')}"
    return str(match.get("document", ""))[:120]
