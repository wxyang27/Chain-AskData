import unittest

from app.knowledge_indexer.retrieval_context import RetrievalContext, RetrievalHit
from app.schema_graph.builder import SchemaGraphBuilder


class SchemaGraphBuilderTestCase(unittest.TestCase):
    def test_builds_schema_graph_from_retrieval_context(self):
        context = RetrievalContext(
            query="截至昨天各门店待核销金额 TOP10",
            metrics=[
                RetrievalHit(
                    document="指标：待核销金额",
                    metadata={"asset_type": "metric", "canonical": "unverified_amount"},
                    distance=0.1,
                    rerank_score=20.0,
                )
            ],
            fields=[
                RetrievalHit(
                    document="字段：left_gmv",
                    metadata={
                        "asset_type": "field",
                        "field_name": "left_gmv",
                        "business_name": "待核销金额",
                        "table_name": "dm_opt_qy_order_info_all_d",
                        "full_name": "soyoung_dw.dm_opt_qy_order_info_all_d.left_gmv",
                    },
                    distance=0.1,
                    rerank_score=20.0,
                ),
                RetrievalHit(
                    document="字段：sy_hospital_name",
                    metadata={
                        "asset_type": "field",
                        "field_name": "sy_hospital_name",
                        "business_name": "门店名称",
                        "table_name": "dim_qy_tenant_info_all_d",
                        "full_name": "soyoung_dw.dim_qy_tenant_info_all_d.sy_hospital_name",
                    },
                    distance=0.1,
                    rerank_score=19.0,
                ),
            ],
            tables=[
                RetrievalHit(
                    document="表：soyoung_dw.dm_opt_qy_order_info_all_d",
                    metadata={
                        "asset_type": "table",
                        "table_name": "dm_opt_qy_order_info_all_d",
                        "full_name": "soyoung_dw.dm_opt_qy_order_info_all_d",
                    },
                    distance=0.1,
                    rerank_score=18.0,
                )
            ],
            relations=[
                RetrievalHit(
                    document="表关系：order_info join tenant_info",
                    metadata={
                        "asset_type": "relation",
                        "left_table": "dm_opt_qy_order_info_all_d",
                        "right_table": "dim_qy_tenant_info_all_d",
                        "usage": "门店维度补充",
                    },
                    distance=0.1,
                    rerank_score=17.0,
                )
            ],
        )

        graph = SchemaGraphBuilder().build(context)

        self.assertEqual(graph.query, "截至昨天各门店待核销金额 TOP10")
        self.assertIn("dm_opt_qy_order_info_all_d", graph.table_names)
        self.assertIn("left_gmv", graph.field_names)
        self.assertIn("unverified_amount", graph.metric_ids)
        self.assertIn("dm_opt_qy_order_info_all_d", graph.schema_graph_text)
        self.assertIn("left_gmv", graph.schema_graph_text)
        self.assertIn("门店维度补充", graph.schema_graph_text)

    def test_marks_missing_evidence_when_no_fields_are_retrieved(self):
        context = RetrievalContext(query="天气对门店收入的影响")

        graph = SchemaGraphBuilder().build(context)

        self.assertIn("fields", graph.missing_evidence)
        self.assertIn("tables", graph.missing_evidence)


if __name__ == "__main__":
    unittest.main()
