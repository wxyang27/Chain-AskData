"""Abstract model client interfaces — Embedding & Rerank.

Current default: HashEmbedding + LightweightReranker (local, deterministic).
Future swap-in: DashScope text-embedding-v4 + qwen-rerank (cloud, higher recall).

Design: Pipeline depends on the interface, not the concrete class.
"""

from app.model_clients.embedding_client import EmbeddingClient
from app.model_clients.rerank_client import RerankClient

__all__ = ["EmbeddingClient", "RerankClient"]
