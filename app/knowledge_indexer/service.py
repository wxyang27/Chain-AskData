from typing import Any

from app.knowledge_indexer.chroma_store import ChromaKnowledgeStore
from app.knowledge_indexer.loader import load_knowledge_chunks
from app.knowledge_indexer.retrieval_context import RetrievalContext, RetrievalContextBuilder


class KnowledgeSearchService:
    """知识库检索服务。"""

    def __init__(self, store: ChromaKnowledgeStore | None = None):
        self.store = store or ChromaKnowledgeStore()
        self.context_builder = RetrievalContextBuilder()

    def search(self, query_text: str, top_k: int = 5) -> list[dict[str, Any]]:
        self._ensure_initialized()
        return self.store.query(query_text, top_k=top_k)

    def search_structured(self, query_text: str, top_k: int = 10) -> RetrievalContext:
        matches = self.search(query_text, top_k=top_k)
        return self.context_builder.build(query_text, matches)

    def _ensure_initialized(self) -> None:
        if self.store.count() > 0:
            return
        self.store.initialize(load_knowledge_chunks(), reset=True)
