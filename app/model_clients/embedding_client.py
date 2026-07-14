"""Embedding client interface.

Current default: HashEmbedding (local, deterministic, 128-dim).
Future: DashScope text-embedding-v4 (cloud, semantic, 1024-dim+).
"""

from abc import ABC, abstractmethod


class EmbeddingClient(ABC):
    """Abstract embedding provider.

    Concrete implementations:
        HashEmbedding  — local, reproducible, no API dependency
        DashScopeEmbedding — cloud, text-embedding-v4, requires API key
    """

    @abstractmethod
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts and return dense vectors."""
        ...

    @abstractmethod
    def embed_query(self, query: str) -> list[float]:
        """Embed a single query text."""
        ...

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Vector dimension of this embedding provider."""
        ...
