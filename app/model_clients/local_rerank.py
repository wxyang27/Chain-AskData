"""Local LightweightReranker adapter.

Implements RerankClient so Pipeline can depend on the interface.
"""

from typing import Any

from app.knowledge_indexer.reranker import LightweightReranker
from app.model_clients.rerank_client import RerankClient


class LocalRerankClient(RerankClient):
    """Adapter wrapping the existing local LightweightReranker."""

    def __init__(self):
        self._reranker = LightweightReranker()

    def rerank(
        self,
        query: str,
        documents: list[str],
        top_n: int,
    ) -> list[dict[str, Any]]:
        # Convert document strings to match dict format expected by reranker
        # The reranker expects items with "document" key
        matches = [
            {"document": doc, "distance": 0.5, "metadata": {"candidate_index": idx}}
            for idx, doc in enumerate(documents)
        ]
        reranked = self._reranker.rerank(query, matches, top_n)
        return [
            {
                "document": item.get("document", ""),
                "score": item.get("rerank_score", 0.0),
                "index": item.get("metadata", {}).get("candidate_index", idx),
            }
            for idx, item in enumerate(reranked)
        ]

    @property
    def provider_name(self) -> str:
        return "lightweight"
