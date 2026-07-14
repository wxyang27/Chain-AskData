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
    source: str = ""  # keyword / vector / rrf / rerank
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SchemaRetrievalTrace:
    """Full trace of the schema retrieval pipeline."""

    query: str
    keywords: list[str] = field(default_factory=list)
    keyword_hits: list[RecallHit] = field(default_factory=list)
    vector_hits: list[RecallHit] = field(default_factory=list)
    rrf_hits: list[RecallHit] = field(default_factory=list)
    rerank_hits: list[RecallHit] = field(default_factory=list)
    selected_fields: list[str] = field(default_factory=list)
    selected_tables: list[str] = field(default_factory=list)
    selected_relations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "keywords": self.keywords,
            "keyword_hit_count": len(self.keyword_hits),
            "vector_hit_count": len(self.vector_hits),
            "rrf_hit_count": len(self.rrf_hits),
            "rerank_hit_count": len(self.rerank_hits),
            "selected_fields": self.selected_fields,
            "selected_tables": self.selected_tables,
            "selected_relations": self.selected_relations,
        }
