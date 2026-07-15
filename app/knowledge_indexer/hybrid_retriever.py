from typing import Any

from app.knowledge_indexer.bm25 import BM25Document, BM25LexicalRetriever
from app.knowledge_indexer.keyword_extractor import KeywordExtractor
from app.knowledge_indexer.reranker import LightweightReranker
from app.knowledge_indexer.types import KnowledgeChunk
from app.model_clients.rerank_client import RerankClient
from app.schema_indexing.loader import SchemaIndexBundle
from app.schema_retrieval.objects import RecallHit, SchemaRetrievalTrace


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
    """Keyword + BM25 + vector retrieval over the current unified knowledge assets."""

    def __init__(
        self,
        chunks: list[KnowledgeChunk],
        keyword_extractor: KeywordExtractor | None = None,
        reranker: LightweightReranker | None = None,
        schema_indexes: SchemaIndexBundle | None = None,
        rerank_client: RerankClient | None = None,
    ):
        self.chunks = chunks
        self.keyword_extractor = keyword_extractor or KeywordExtractor()
        self.reranker = reranker or LightweightReranker()
        self.schema_indexes = schema_indexes
        self.rerank_client = rerank_client  # optional pluggable reranker
        self.last_rerank_provider = "lightweight"
        self.last_rerank_fallback = False
        self.last_rerank_fallback_reason = ""
        self.bm25_retriever = BM25LexicalRetriever(self._build_bm25_documents())

    def retrieve(
        self,
        query_text: str,
        vector_matches: list[dict[str, Any]],
        top_k: int,
    ) -> list[dict[str, Any]]:
        keyword_matches = self._keyword_retrieve(query_text, limit=max(top_k * 4, 20))
        bm25_matches = self._bm25_retrieve(query_text, limit=max(top_k * 4, 20))
        schema_index_matches = self._schema_index_retrieve(query_text, limit=max(top_k * 4, 20))
        normalized_vector_matches = [
            self._normalize_vector_match(match)
            for match in vector_matches
        ]
        fused = reciprocal_rank_fusion(
            [keyword_matches, bm25_matches, schema_index_matches, normalized_vector_matches],
        )
        candidates = [
            {
                "document": item.get("document", ""),
                "metadata": item.get("metadata", {}) or {},
                "distance": float(item.get("distance", 1.0)) - float(item.get("rrf_score", 0.0)),
            }
            for item in fused
        ]
        return self._apply_rerank(query_text, candidates, top_k)

    def retrieve_with_trace(
        self,
        query_text: str,
        vector_matches: list[dict[str, Any]],
        top_k: int,
    ) -> tuple[list[dict[str, Any]], SchemaRetrievalTrace]:
        """Retrieve with full observability trace.

        Returns (final_matches, trace) so callers can inspect
        keyword / BM25 / vector / RRF / rerank stages independently.
        """
        trace = SchemaRetrievalTrace(query=query_text)
        keywords = self.keyword_extractor.extract(query_text)
        trace.keywords = keywords

        # --- keyword recall ---
        keyword_matches = self._keyword_retrieve(query_text, limit=max(top_k * 4, 20))
        trace.keyword_hits = [
            RecallHit(
                id=m.get("id", ""),
                asset_type=(m.get("metadata") or {}).get("asset_type", ""),
                name=(m.get("metadata") or {}).get("field_name")
                     or (m.get("metadata") or {}).get("metric_name")
                     or (m.get("metadata") or {}).get("table_name", ""),
                score=float(m.get("keyword_score", 0)),
                source="keyword",
                metadata=m.get("metadata", {}),
            )
            for m in keyword_matches[:20]
        ]

        # --- BM25 lexical recall ---
        bm25_matches = self._bm25_retrieve(query_text, limit=max(top_k * 4, 20))
        trace.bm25_hits = [
            RecallHit(
                id=m.get("id", ""),
                asset_type=(m.get("metadata") or {}).get("asset_type", ""),
                name=(m.get("metadata") or {}).get("field_name")
                     or (m.get("metadata") or {}).get("metric_name")
                     or (m.get("metadata") or {}).get("table_name", ""),
                score=float(m.get("bm25_score", 0)),
                source="bm25",
                metadata=m.get("metadata", {}),
            )
            for m in bm25_matches[:20]
        ]

        # --- vector recall ---
        normalized_vector_matches = [
            self._normalize_vector_match(match)
            for match in vector_matches
        ]
        trace.vector_hits = [
            RecallHit(
                id=_match_id(m),
                asset_type=(m.get("metadata") or {}).get("asset_type", ""),
                name=(m.get("metadata") or {}).get("field_name")
                     or (m.get("metadata") or {}).get("metric_name")
                     or "",
                score=float(m.get("distance", 0)),
                source="vector",
                metadata=m.get("metadata", {}),
            )
            for m in normalized_vector_matches[:20]
        ]

        # --- schema index recall ---
        schema_index_matches = self._schema_index_retrieve(
            query_text, limit=max(top_k * 4, 20),
        )

        # --- RRF fusion ---
        fused = reciprocal_rank_fusion(
            [keyword_matches, bm25_matches, schema_index_matches, normalized_vector_matches],
        )
        trace.rrf_hits = [
            RecallHit(
                id=_match_id(item),
                asset_type=(item.get("metadata") or {}).get("asset_type", ""),
                name=(item.get("metadata") or {}).get("field_name")
                     or (item.get("metadata") or {}).get("metric_name", ""),
                score=float(item.get("rrf_score", 0)),
                source="rrf",
                metadata=item.get("metadata", {}),
            )
            for item in fused[:30]
        ]

        # --- rerank ---
        candidates = [
            {
                "document": item.get("document", ""),
                "metadata": item.get("metadata", {}) or {},
                "distance": float(item.get("distance", 1.0)) - float(item.get("rrf_score", 0.0)),
            }
            for item in fused
        ]
        reranked = self._apply_rerank(query_text, candidates, top_k)
        trace.rerank_provider = self.last_rerank_provider
        trace.rerank_fallback = self.last_rerank_fallback
        trace.rerank_fallback_reason = self.last_rerank_fallback_reason
        trace.rerank_hits = [
            RecallHit(
                id=_match_id(m),
                asset_type=(m.get("metadata") or {}).get("asset_type", ""),
                name=(m.get("metadata") or {}).get("field_name")
                     or (m.get("metadata") or {}).get("metric_name", ""),
                score=float(m.get("rerank_score", 0)),
                source="rerank",
                metadata=m.get("metadata", {}),
            )
            for m in reranked[:top_k]
        ]

        return reranked, trace

    def _apply_rerank(
        self,
        query_text: str,
        candidates: list[dict[str, Any]],
        top_k: int,
    ) -> list[dict[str, Any]]:
        """Apply reranker — pluggable client or local default."""
        self.last_rerank_provider = (
            self.rerank_client.provider_name if self.rerank_client is not None else "lightweight"
        )
        self.last_rerank_fallback = False
        self.last_rerank_fallback_reason = ""

        if self.rerank_client is not None and self.rerank_client.provider_name != "lightweight":
            try:
                docs = [c.get("document", "") for c in candidates]
                results = self.rerank_client.rerank(query_text, docs, top_k)
                reranked = []
                for r_item in results:
                    idx = int(r_item.get("index", 0))
                    if 0 <= idx < len(candidates):
                        c = candidates[idx].copy()
                        c["rerank_score"] = r_item.get("score", 0.0)
                        c["rerank_provider"] = self.rerank_client.provider_name
                        reranked.append(c)
                return reranked[:top_k]
            except Exception as exc:
                self.last_rerank_fallback = True
                self.last_rerank_fallback_reason = str(exc)
        # Default: local LightweightReranker
        self.last_rerank_provider = "lightweight"
        reranked = self.reranker.rerank(query_text, candidates, top_k)
        for item in reranked:
            item["rerank_provider"] = "lightweight"
            item["rerank_fallback"] = self.last_rerank_fallback
            if self.last_rerank_fallback_reason:
                item["rerank_fallback_reason"] = self.last_rerank_fallback_reason
        return reranked

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

    def _bm25_retrieve(self, query_text: str, limit: int) -> list[dict[str, Any]]:
        return self.bm25_retriever.search(query_text, top_k=limit)

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

    def _build_bm25_documents(self) -> list[BM25Document]:
        documents: list[BM25Document] = []

        for chunk in self.chunks:
            searchable = chunk.document + "\n" + " ".join(
                str(value) for value in chunk.metadata.values()
            )
            documents.append(
                BM25Document(
                    id=chunk.chunk_id,
                    text=searchable,
                    payload={
                        "document": chunk.document,
                        "metadata": chunk.metadata,
                    },
                )
            )

        if not self.schema_indexes:
            return documents

        for row in self.schema_indexes.schema_field_keyword_index:
            field_id = row["field_id"]
            detail = self.schema_indexes.field_detail_by_id.get(field_id, {})
            rerank = self.schema_indexes.field_rerank_by_id.get(field_id, {})
            metadata = {
                **row,
                **detail,
                "asset_type": "field",
                "full_name": self._field_full_name(detail or row),
            }
            document = rerank.get("rerank_text") or row.get("keyword_text", "")
            documents.append(
                BM25Document(
                    id=f"field:{field_id}",
                    text="\n".join([document, row.get("keyword_text", ""), str(metadata)]),
                    payload={
                        "document": document,
                        "metadata": metadata,
                    },
                )
            )

        for row in self.schema_indexes.metric_keyword_index:
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
            document = rerank.get("rerank_text") or row.get("keyword_text", "")
            documents.append(
                BM25Document(
                    id=f"metric:{metric_id}",
                    text="\n".join([document, row.get("keyword_text", ""), str(metadata)]),
                    payload={
                        "document": document,
                        "metadata": metadata,
                    },
                )
            )

        for row in self.schema_indexes.schema_table_index:
            metadata = {**row, "asset_type": "table"}
            document = row.get("table_summary") or row.get("full_name", "")
            documents.append(
                BM25Document(
                    id=f"table:{row['table_name']}",
                    text="\n".join([document, str(metadata)]),
                    payload={
                        "document": document,
                        "metadata": metadata,
                    },
                )
            )

        return documents

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
