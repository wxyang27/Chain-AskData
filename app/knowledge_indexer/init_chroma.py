import os

from app.knowledge_indexer.chroma_store import ChromaKnowledgeStore
from app.knowledge_indexer.loader import load_knowledge_chunks
from app.knowledge_indexer.types import ChromaInitResult


def initialize_chroma_from_assets(
    reset: bool = True,
    include_generated: bool = True,
) -> ChromaInitResult:
    """从 knowledge 目录初始化本地 ChromaDB。"""

    persist_dir = os.getenv("CHROMA_PERSIST_DIR", "data/chroma")
    collection_name = os.getenv("CHROMA_COLLECTION_NAME", "chain_askdata_knowledge")
    chunks = load_knowledge_chunks(include_generated=include_generated)
    store = ChromaKnowledgeStore(
        persist_dir=persist_dir,
        collection_name=collection_name,
    )
    return store.initialize(chunks, reset=reset)


def main() -> None:
    result = initialize_chroma_from_assets(reset=True)
    print(
        "ChromaDB 初始化完成："
        f"collection={result.collection_name}, "
        f"chunks={result.chunk_count}, "
        f"persist_dir={result.persist_dir}"
    )


if __name__ == "__main__":
    main()
