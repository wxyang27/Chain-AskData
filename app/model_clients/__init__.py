"""Abstract model client interfaces — Embedding, Rerank, Executor.

Current default: HashEmbedding + LightweightReranker + MockExecutor (local).
Future swap-in: DashScope text-embedding-v4 + qwen-rerank + MaxComputeExecutor.

Design: Pipeline depends on the interface, not the concrete class.
Each client can be swapped independently without changing pipeline logic.
"""

from app.model_clients.embedding_client import EmbeddingClient
from app.model_clients.executor_client import ExecutorClient
from app.model_clients.rerank_client import RerankClient

__all__ = ["EmbeddingClient", "ExecutorClient", "RerankClient"]

