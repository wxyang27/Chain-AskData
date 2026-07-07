import tempfile
import unittest

from app.knowledge_indexer.chroma_store import ChromaKnowledgeStore
from app.knowledge_indexer.loader import load_knowledge_chunks


class ChromaKnowledgeTestCase(unittest.TestCase):
    """ChromaDB 知识库初始化与检索测试。"""

    def test_loads_knowledge_chunks_with_readable_chinese_metadata(self):
        chunks = load_knowledge_chunks()

        self.assertGreaterEqual(len(chunks), 20)
        self.assertTrue(any(chunk.metadata["asset_type"] == "metric" for chunk in chunks))
        self.assertTrue(any(chunk.metadata["asset_type"] == "field" for chunk in chunks))
        self.assertTrue(any(chunk.metadata["asset_type"] == "table" for chunk in chunks))
        self.assertTrue(any("指标：核销客单价" in chunk.document for chunk in chunks))
        self.assertTrue(any("字段：exe_income" in chunk.document for chunk in chunks))
        self.assertFalse(any("閿?" in chunk.document for chunk in chunks))
        self.assertFalse(any("閺?" in chunk.document for chunk in chunks))

    def test_initializes_chroma_collection_and_reranks_exact_metric_first(self):
        chunks = load_knowledge_chunks()

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
            store = ChromaKnowledgeStore(
                persist_dir=temp_dir,
                collection_name="test_chain_askdata_knowledge",
            )

            result = store.initialize(chunks, reset=True)
            matches = store.query("核销客单价的分母是什么", top_k=3)
            first_match = store.query("核销客单价的分母是什么", top_k=1)

        self.assertEqual(result.collection_name, "test_chain_askdata_knowledge")
        self.assertEqual(result.chunk_count, len(chunks))
        self.assertGreaterEqual(result.chunk_count, 20)
        self.assertEqual(matches[0]["metadata"].get("canonical"), "execution_aov_by_visit")
        self.assertGreater(matches[0]["rerank_score"], 0)
        self.assertEqual(first_match[0]["metadata"].get("canonical"), "execution_aov_by_visit")
        self.assertEqual(store.collection_count("metric_schema_collection"), 11)
        self.assertEqual(store.collection_count("table_field_schema_collection"), 11)
        self.assertEqual(store.collection_count("sql_example_collection"), 13)


if __name__ == "__main__":
    unittest.main()
