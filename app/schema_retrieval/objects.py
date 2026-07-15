"""Observable objects for Schema Retrieval — recall hits & trace.

Makes the RAG pipeline explicit: keyword → vector → RRF → rerank → selected.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RecallHit:
    """Single recall result from any retrieval path."""

    id: str
    asset_type: str  # metric / field / table / relation / demo_query
    name: str = ""
    score: float = 0.0
    source: str = ""  # keyword / bm25 / vector / rrf / rerank
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SchemaRetrievalTrace:
    """Full trace of the schema retrieval pipeline."""

    query: str
    keywords: list[str] = field(default_factory=list)
    keyword_hits: list[RecallHit] = field(default_factory=list)
    bm25_hits: list[RecallHit] = field(default_factory=list)
    vector_hits: list[RecallHit] = field(default_factory=list)
    rrf_hits: list[RecallHit] = field(default_factory=list)
    rerank_hits: list[RecallHit] = field(default_factory=list)
    selected_fields: list[str] = field(default_factory=list)
    selected_tables: list[str] = field(default_factory=list)
    selected_relations: list[str] = field(default_factory=list)
    rerank_provider: str = ""
    rerank_fallback: bool = False
    rerank_fallback_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        keyword_fields = self._field_names(self.keyword_hits)
        bm25_fields = self._field_names(self.bm25_hits)
        vector_fields = self._field_names(self.vector_hits)
        rrf_fields = self._field_names(self.rrf_hits)
        rerank_fields = self._field_names(self.rerank_hits)
        return {
            "query": self.query,
            "keywords": self.keywords,
            "keyword_hit_count": len(self.keyword_hits),
            "bm25_hit_count": len(self.bm25_hits),
            "vector_hit_count": len(self.vector_hits),
            "rrf_hit_count": len(self.rrf_hits),
            "rerank_hit_count": len(self.rerank_hits),
            "keyword_fields": keyword_fields,
            "bm25_fields": bm25_fields,
            "vector_fields": vector_fields,
            "rrf_fields": rrf_fields,
            "rerank_fields": rerank_fields,
            "bm25_only_fields": sorted(set(bm25_fields) - set(keyword_fields)),
            "vector_only_fields": sorted(set(vector_fields) - set(keyword_fields)),
            "rerank_provider": self.rerank_provider,
            "rerank_fallback": self.rerank_fallback,
            "rerank_fallback_reason": self.rerank_fallback_reason,
            "selected_fields": self.selected_fields,
            "selected_tables": self.selected_tables,
            "selected_relations": self.selected_relations,
        }

    def _field_names(self, hits: list[RecallHit]) -> list[str]:
        return sorted({
            hit.metadata.get("field_name", "")
            for hit in hits
            if hit.metadata.get("asset_type") == "field" and hit.metadata.get("field_name")
        })
