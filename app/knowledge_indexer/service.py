from typing import Any

from app.knowledge_indexer.chroma_store import ChromaKnowledgeStore
from app.knowledge_indexer.hybrid_retriever import HybridRetriever
from app.knowledge_indexer.loader import load_knowledge_chunks
from app.knowledge_indexer.retrieval_context import RetrievalContext, RetrievalContextBuilder
from app.schema_index.loader import SchemaIndexLoader


class KnowledgeSearchService:
    """知识库检索服务。"""

    def __init__(
        self,
        store: ChromaKnowledgeStore | None = None,
        include_generated: bool = True,
        generated_dir: str = "knowledge/generated",
        indexes_dir: str = "knowledge/generated/indexes",
    ):
        self.store = store or ChromaKnowledgeStore()
        self.context_builder = RetrievalContextBuilder()
        self.chunks = load_knowledge_chunks(
            include_generated=include_generated,
            generated_dir=generated_dir,
        )
        self.schema_indexes = SchemaIndexLoader().load(indexes_dir)
        self.hybrid_retriever = HybridRetriever(
            self.chunks,
            schema_indexes=self.schema_indexes,
        )

    def search(self, query_text: str, top_k: int = 5) -> list[dict[str, Any]]:
        self._ensure_initialized()
        vector_matches = self.store.query(query_text, top_k=max(top_k, 10))
        return self.hybrid_retriever.retrieve(
            query_text=query_text,
            vector_matches=vector_matches,
            top_k=top_k,
        )

    def search_structured(self, query_text: str, top_k: int = 10) -> RetrievalContext:
        matches = self.search(query_text, top_k=top_k)
        return self.context_builder.build(query_text, matches)

    def search_structured_with_trace(
        self,
        query_text: str,
        top_k: int = 10,
    ) -> tuple[RetrievalContext, dict[str, Any]]:
        """Search knowledge assets and expose recall-stage trace.

        This keeps Pipeline orchestration clean: callers do not need to know
        about Chroma, vector matches, RRF, or rerank internals.
        """

        self._ensure_initialized()
        vector_matches = self.store.query(query_text, top_k=max(top_k, 10))

        if hasattr(self.hybrid_retriever, "retrieve_with_trace"):
            matches, trace = self.hybrid_retriever.retrieve_with_trace(
                query_text=query_text,
                vector_matches=vector_matches,
                top_k=top_k,
            )
            return self.context_builder.build(query_text, matches), trace.to_dict()

        matches = self.hybrid_retriever.retrieve(
            query_text=query_text,
            vector_matches=vector_matches,
            top_k=top_k,
        )
        return self.context_builder.build(query_text, matches), {}

    def _ensure_initialized(self) -> None:
        if self.store.count() > 0:
            return
        self.store.initialize(self.chunks, reset=True)
