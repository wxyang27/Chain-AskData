from pathlib import Path
from typing import Any

import chromadb

from app.knowledge_indexer.embeddings import HashEmbedding
from app.knowledge_indexer.reranker import LightweightReranker
from app.knowledge_indexer.types import ChromaInitResult, KnowledgeChunk


TYPED_COLLECTIONS = {
    "metric": "metric_schema_collection",
    "table": "table_field_schema_collection",
    "relation": "table_field_schema_collection",
    "demo_query": "sql_example_collection",
}


class ChromaKnowledgeStore:
    """Chain-AskData 本地 ChromaDB 知识库。"""

    def __init__(
        self,
        persist_dir: str = "data/chroma",
        collection_name: str = "chain_askdata_knowledge",
        embedding: HashEmbedding | None = None,
        reranker: LightweightReranker | None = None,
    ):
        self.persist_dir = persist_dir
        self.collection_name = collection_name
        self.embedding = embedding or HashEmbedding()
        self.reranker = reranker or LightweightReranker()
        Path(self.persist_dir).mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(path=self.persist_dir)

    def initialize(self, chunks: list[KnowledgeChunk], reset: bool = False) -> ChromaInitResult:
        if reset:
            self._delete_collection_if_exists()
            for collection_name in set(TYPED_COLLECTIONS.values()):
                self._delete_collection_if_exists(collection_name)

        collection = self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )

        documents = [chunk.document for chunk in chunks]
        collection.upsert(
            ids=[chunk.chunk_id for chunk in chunks],
            documents=documents,
            metadatas=[chunk.metadata for chunk in chunks],
            embeddings=self.embedding.embed_many(documents),
        )
        self._initialize_typed_collections(chunks)

        return ChromaInitResult(
            persist_dir=self.persist_dir,
            collection_name=self.collection_name,
            chunk_count=len(chunks),
        )

    def query(self, query_text: str, top_k: int = 5) -> list[dict[str, Any]]:
        collection = self.client.get_or_create_collection(name=self.collection_name)
        collection_count = collection.count()
        candidate_count = min(max(top_k * 20, 100), collection_count) if collection_count else top_k
        result = collection.query(
            query_embeddings=[self.embedding.embed(query_text)],
            n_results=candidate_count,
            include=["documents", "metadatas", "distances"],
        )

        documents = result.get("documents", [[]])[0]
        metadatas = result.get("metadatas", [[]])[0]
        distances = result.get("distances", [[]])[0]
        matches = [
            {
                "document": document,
                "metadata": metadata,
                "distance": distance,
            }
            for document, metadata, distance in zip(documents, metadatas, distances)
        ]

        return self.reranker.rerank(query_text, matches, top_k)

    def count(self) -> int:
        collection = self.client.get_or_create_collection(name=self.collection_name)
        return collection.count()

    def collection_count(self, collection_name: str) -> int:
        collection = self.client.get_or_create_collection(name=collection_name)
        return collection.count()

    def _initialize_typed_collections(self, chunks: list[KnowledgeChunk]) -> None:
        grouped_chunks: dict[str, list[KnowledgeChunk]] = {}
        for chunk in chunks:
            asset_type = chunk.metadata.get("asset_type", "")
            collection_name = TYPED_COLLECTIONS.get(asset_type)
            if not collection_name:
                continue
            grouped_chunks.setdefault(collection_name, []).append(chunk)

        for collection_name, typed_chunks in grouped_chunks.items():
            collection = self.client.get_or_create_collection(
                name=collection_name,
                metadata={"hnsw:space": "cosine"},
            )
            documents = [chunk.document for chunk in typed_chunks]
            collection.upsert(
                ids=[chunk.chunk_id for chunk in typed_chunks],
                documents=documents,
                metadatas=[chunk.metadata for chunk in typed_chunks],
                embeddings=self.embedding.embed_many(documents),
            )

    def _delete_collection_if_exists(self, collection_name: str | None = None) -> None:
        try:
            self.client.delete_collection(collection_name or self.collection_name)
        except Exception:
            return
