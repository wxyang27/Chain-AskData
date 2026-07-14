"""Abstract model client interfaces — Embedding and Rerank.

Current default: HashEmbedding + LightweightReranker (local).
Future swap-in: DashScope text-embedding-v4 + qwen-rerank.

Design: Pipeline depends on the interface, not the concrete class.
Each client can be swapped independently without changing pipeline logic.
"""

from app.model_clients.embedding_client import EmbeddingClient
from app.model_clients.rerank_client import RerankClient

__all__ = ["EmbeddingClient", "RerankClient"]
