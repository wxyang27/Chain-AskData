import tempfile
import unittest

from app.knowledge_indexer.chroma_store import ChromaKnowledgeStore
from app.knowledge_indexer.loader import load_knowledge_chunks
from app.knowledge_indexer.retrieval_context import RetrievalContextBuilder
from app.cot_planning.planner import QueryPlanner


class FieldSchemaRetrievalTestCase(unittest.TestCase):
    """字段级 Schema 检索与 QueryPlan 采纳测试。"""

    def test_loads_field_chunks_for_mvp_caliber_fields(self):
        chunks = load_knowledge_chunks()
        field_chunks = [
            chunk
            for chunk in chunks
            if chunk.metadata.get("asset_type") == "field"
        ]
        field_names = {chunk.metadata["field_name"] for chunk in field_chunks}

        self.assertIn("exe_income", field_names)
        self.assertIn("exe_amount", field_names)
        self.assertIn("customer_id", field_names)
        self.assertIn("verify_date_id", field_names)
        self.assertIn("pay_gmv", field_names)
        self.assertIn("left_gmv", field_names)
        self.assertTrue(any("字段：exe_income" in chunk.document for chunk in field_chunks))

    def test_retrieves_execution_user_count_fields(self):
        chunks = load_knowledge_chunks()

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
            store = ChromaKnowledgeStore(
                persist_dir=temp_dir,
                collection_name="test_field_schema_retrieval",
            )
            store.initialize(chunks, reset=True)
            matches = store.query("核销人数应该用哪个字段", top_k=10)

        context = RetrievalContextBuilder().build("核销人数应该用哪个字段", matches)

        self.assertIn("customer_id", context.top_field_names(limit=5))

    def test_retrieves_unverified_amount_fields(self):
        chunks = load_knowledge_chunks()

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
            store = ChromaKnowledgeStore(
                persist_dir=temp_dir,
                collection_name="test_unverified_field_schema",
            )
            store.initialize(chunks, reset=True)
            matches = store.query("待核销金额 TOP10 用哪些字段", top_k=10)

        context = RetrievalContextBuilder().build("待核销金额 TOP10 用哪些字段", matches)
        field_names = context.top_field_names(limit=8)

        self.assertIn("left_gmv", field_names)
        self.assertIn("left_num", field_names)

    def test_query_plan_records_retrieved_field_evidence(self):
        context = RetrievalContextBuilder().build(
            "核销人数应该用哪个字段",
            [
                {
                    "document": "字段：customer_id\n业务含义：核销人数去重客户 ID",
                    "metadata": {
                        "asset_type": "field",
                        "field_name": "customer_id",
                        "table_name": "dm_opt_qy_user_execution_record_all_d",
                        "full_name": "soyoung_dw.dm_opt_qy_user_execution_record_all_d.customer_id",
                    },
                    "distance": 0.1,
                    "rerank_score": 18.0,
                }
            ],
        )

        plan = QueryPlanner().plan("核销人数应该用哪个字段", retrieval_context=context)

        self.assertIn("customer_id", plan.retrieved_field_names)
        self.assertTrue(any("customer_id" in item for item in plan.schema_evidence))


if __name__ == "__main__":
    unittest.main()
