"""Local HashEmbedding adapter — wraps existing app/knowledge_indexer/embeddings.py.

Implements EmbeddingClient so Pipeline can depend on the interface.
"""

from app.knowledge_indexer.embeddings import HashEmbedding
from app.model_clients.embedding_client import EmbeddingClient


class LocalHashEmbeddingClient(EmbeddingClient):
    """Adapter wrapping the existing local HashEmbedding (128-dim MD5)."""

    def __init__(self, dimension: int = 128):
        self._hash = HashEmbedding(dimension=dimension)

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self._hash.embed(t) for t in texts]

    def embed_query(self, query: str) -> list[float]:
        return self._hash.embed(query)

    @property
    def dimension(self) -> int:
        return self._hash.dimension

    @property
    def provider_name(self) -> str:
        return "local"

    @property
    def model_name(self) -> str:
        return f"hash-{self.dimension}"
