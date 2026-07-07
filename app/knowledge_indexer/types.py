from dataclasses import dataclass


@dataclass(frozen=True)
class KnowledgeChunk:
    """写入向量库的最小知识单元。"""

    chunk_id: str
    document: str
    metadata: dict[str, str]


@dataclass(frozen=True)
class ChromaInitResult:
    """ChromaDB 初始化结果。"""

    persist_dir: str
    collection_name: str
    chunk_count: int
