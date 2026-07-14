"""Unified offline build entry point.

Builds all schema indexes from generated assets and initializes ChromaDB.

Usage:
    PYTHONPATH=. python -m app.schema_indexing.build_indexes
"""

import json
import sys
from pathlib import Path

from app.assets.loader import load_yaml_asset
from app.knowledge_indexer.chroma_store import ChromaKnowledgeStore
from app.knowledge_indexer.loader import load_knowledge_chunks
from app.model_clients.factory import create_embedding_client, create_rerank_client
from app.schema_indexing.builder import SchemaIndexBuilder


INDEXES_DIR = Path("knowledge/generated/indexes")
ASSETS_DIR = Path("knowledge/generated")
OUTPUTS = [
    "schema_field_keyword_index.json",
    "schema_field_vector_index.json",
    "schema_field_rerank_index.json",
    "schema_table_index.json",
    "schema_field_detail_index.json",
    "schema_relation_index.json",
    "metric_keyword_index.json",
    "metric_rerank_index.json",
]


def _load_asset(name: str) -> list:
    path = ASSETS_DIR / name
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return []


def build_indexes() -> dict[str, int]:
    """Build all schema indexes and ChromaDB, return summary counts."""
    print("=" * 60)
    print("  Chain-AskData Offline Build")
    print("=" * 60)

    # 1. Load generated assets
    print("\n[1/3] Loading generated assets ...")
    metrics = _load_asset("metrics_full.json")
    fields = _load_asset("fields_merged.json")
    tables = _load_asset("tables_full.json")

    print(f"  metrics: {len(metrics)}")
    print(f"  fields:  {len(fields)}")
    print(f"  tables:  {len(tables)}")

    # 2. Build indexes
    print("\n[2/3] Building schema indexes ...")
    INDEXES_DIR.mkdir(parents=True, exist_ok=True)
    builder = SchemaIndexBuilder()
    indexes = builder.build(metrics, fields, tables)

    summary = {}
    for filename, rows in indexes.items():
        path = INDEXES_DIR / filename
        path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
        summary[filename] = len(rows)
        print(f"  {filename}: {len(rows)} rows")

    # 3. Initialize ChromaDB
    print("\n[3/3] Initializing ChromaDB ...")
    emb = create_embedding_client()
    store = ChromaKnowledgeStore(embedding=emb)
    chunks = load_knowledge_chunks(include_generated=True, generated_dir=str(ASSETS_DIR))
    store.initialize(chunks, reset=True)
    print(f"  collection: {store.collection_name}")
    print(f"  chunks:     {store.count()}")
    print(f"  embedding:  {getattr(emb, 'provider_name', emb.__class__.__name__)}/"
          f"{getattr(emb, 'model_name', '')} dim={emb.dimension}")

    # 4. Write manifest
    print("\n[4/4] Writing index manifest ...")
    from datetime import datetime, timezone
    rerank = create_rerank_client()
    manifest = {
        "embedding_provider": getattr(emb, "provider_name", emb.__class__.__name__),
        "embedding_model": getattr(emb, "model_name", ""),
        "embedding_dimension": emb.dimension,
        "rerank_provider": rerank.provider_name,
        "chroma_persist_dir": store.persist_dir,
        "chroma_collection": store.collection_name,
        "build_time": datetime.now(timezone.utc).isoformat(),
        "chunk_count": store.count(),
    }
    manifest_path = INDEXES_DIR / "index_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  manifest: {json.dumps(manifest, ensure_ascii=False)}")

    print("\n" + "=" * 60)
    print("  Build complete.")
    print(f"  Indexes: {INDEXES_DIR.resolve()}")
    print(f"  ChromaDB: data/chroma")
    print("=" * 60)

    return summary


if __name__ == "__main__":
    build_indexes()
