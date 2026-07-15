import unittest

from app.knowledge_indexer.hybrid_retriever import HybridRetriever, reciprocal_rank_fusion
from app.knowledge_indexer.keyword_extractor import KeywordExtractor
from app.knowledge_indexer.loader import load_knowledge_chunks
from app.knowledge_indexer.service import KnowledgeSearchService
from app.schema_indexing.loader import SchemaIndexLoader


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

    def test_bm25_route_recalls_schema_fields_and_trace(self):
        schema_indexes = SchemaIndexLoader().load()
        retriever = HybridRetriever(chunks=[], schema_indexes=schema_indexes)

        matches, trace = retriever.retrieve_with_trace(
            "最近30天新客支付GMV是多少",
            vector_matches=[],
            top_k=8,
        )

        field_names = [match["metadata"].get("field_name") for match in matches]
        trace_dict = trace.to_dict()

        self.assertGreater(trace_dict["bm25_hit_count"], 0)
        self.assertIn("pay_gmv", trace_dict["bm25_fields"])
        self.assertIn("pay_gmv", field_names)

    def test_knowledge_search_service_uses_hybrid_retrieval(self):
        context = KnowledgeSearchService().search_structured("核销人数应该用哪个字段", top_k=8)

        self.assertIn("customer_id", context.top_field_names(limit=5))

    def test_hybrid_retriever_consumes_schema_index_loader(self):
        schema_indexes = SchemaIndexLoader().load()
        retriever = HybridRetriever(chunks=[], schema_indexes=schema_indexes)

        matches = retriever.retrieve("exe_income A002", vector_matches=[], top_k=5)
        field_ids = [match["metadata"].get("field_id") for match in matches]
        metric_ids = [match["metadata"].get("metric_id") for match in matches]

        self.assertIn("dm_opt_qy_user_execution_record_all_d.exe_income", field_ids)
        self.assertIn("A002", metric_ids)


if __name__ == "__main__":
    unittest.main()
