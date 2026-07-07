import unittest

from app.knowledge_indexer.hybrid_retriever import HybridRetriever, reciprocal_rank_fusion
from app.knowledge_indexer.keyword_extractor import KeywordExtractor
from app.knowledge_indexer.loader import load_knowledge_chunks
from app.knowledge_indexer.service import KnowledgeSearchService


class HybridRetrieverTestCase(unittest.TestCase):
    def test_keyword_extractor_keeps_business_terms_and_field_names(self):
        keywords = KeywordExtractor().extract("核销人数应该用 customer_id 还是 uid")

        self.assertIn("核销人数", keywords)
        self.assertIn("customer_id", keywords)
        self.assertIn("uid", keywords)

    def test_rrf_merges_keyword_and_vector_rankings(self):
        fused = reciprocal_rank_fusion(
            [
                [{"id": "field:customer_id"}, {"id": "metric:execution_user_count"}],
                [{"id": "metric:execution_user_count"}, {"id": "field:customer_id"}],
            ]
        )

        self.assertEqual({item["id"] for item in fused}, {"field:customer_id", "metric:execution_user_count"})
        self.assertGreater(fused[0]["rrf_score"], 0)

    def test_hybrid_retriever_returns_keyword_matched_field(self):
        retriever = HybridRetriever(load_knowledge_chunks())

        matches = retriever.retrieve("核销人数应该用哪个字段", vector_matches=[], top_k=5)
        field_names = [match["metadata"].get("field_name") for match in matches]

        self.assertIn("customer_id", field_names)

    def test_knowledge_search_service_uses_hybrid_retrieval(self):
        context = KnowledgeSearchService().search_structured("核销人数应该用哪个字段", top_k=8)

        self.assertIn("customer_id", context.top_field_names(limit=5))


if __name__ == "__main__":
    unittest.main()
