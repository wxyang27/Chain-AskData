from pathlib import Path

from app.knowledge_importer.chunker import load_generated_knowledge_chunks
from app.knowledge_importer.pipeline import PrimaryKnowledgeImporter
from app.knowledge_indexer.chroma_store import ChromaKnowledgeStore
from app.knowledge_indexer.keyword_extractor import KeywordExtractor
from app.knowledge_indexer.loader import load_knowledge_chunks
from app.knowledge_indexer.service import KnowledgeSearchService


def test_generated_assets_become_searchable_knowledge_chunks(tmp_path):
    PrimaryKnowledgeImporter().import_to_directory(Path("docs/primary_knowledge"), tmp_path)

    chunks = load_generated_knowledge_chunks(tmp_path)
    chunk_ids = {chunk.chunk_id for chunk in chunks}

    assert "generated_metric:A002" in chunk_ids
    assert any(chunk.metadata["asset_type"] == "table" for chunk in chunks)
    assert any(chunk.metadata["asset_type"] == "business_playbook" for chunk in chunks)
    assert any("核销收入" in chunk.document for chunk in chunks)
    assert all(
        isinstance(value, str)
        for chunk in chunks
        for value in chunk.metadata.values()
    )


def test_generated_assets_are_loaded_only_when_explicitly_requested(tmp_path):
    PrimaryKnowledgeImporter().import_to_directory(Path("docs/primary_knowledge"), tmp_path)

    default_chunk_ids = {chunk.chunk_id for chunk in load_knowledge_chunks()}
    generated_chunk_ids = {
        chunk.chunk_id
        for chunk in load_knowledge_chunks(
            include_generated=True,
            generated_dir=tmp_path,
        )
    }

    assert "generated_metric:A002" not in default_chunk_ids
    assert "generated_metric:A002" in generated_chunk_ids


def test_knowledge_search_service_can_consume_generated_assets(tmp_path):
    generated_dir = tmp_path / "generated"
    chroma_dir = tmp_path / "chroma"
    PrimaryKnowledgeImporter().import_to_directory(Path("docs/primary_knowledge"), generated_dir)

    service = KnowledgeSearchService(
        store=ChromaKnowledgeStore(
            persist_dir=str(chroma_dir),
            collection_name="test_generated_service",
        ),
        include_generated=True,
        generated_dir=str(generated_dir),
    )

    context = service.search_structured("核销收入是什么", top_k=5)

    assert "A002" in context.top_metric_ids(limit=5)


def test_keyword_extractor_keeps_generated_metric_names():
    keywords = KeywordExtractor().extract("\u6838\u9500\u6536\u5165\u662f\u4ec0\u4e48")

    assert "\u6838\u9500\u6536\u5165" in keywords
