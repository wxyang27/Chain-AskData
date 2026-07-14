import unittest

from app.knowledge_indexer.retrieval_context import RetrievalContext, RetrievalHit
from app.schema_graph.builder import SchemaGraphBuilder, format_schema_graph
from app.schema_indexing.loader import SchemaIndexLoader


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

    def test_builds_and_formats_schema_graph_from_schema_index_loader(self):
        context = RetrievalContext(
            query="exe_income by tenant",
            fields=[
                RetrievalHit(
                    document="field exe_income",
                    metadata={
                        "asset_type": "field",
                        "field_id": "dm_opt_qy_user_execution_record_all_d.exe_income",
                        "field_name": "exe_income",
                        "table_name": "dm_opt_qy_user_execution_record_all_d",
                    },
                    distance=0.1,
                    rerank_score=20.0,
                ),
                RetrievalHit(
                    document="field sy_hospital_name",
                    metadata={
                        "asset_type": "field",
                        "field_id": "dim_qy_tenant_info_all_d.sy_hospital_name",
                        "field_name": "sy_hospital_name",
                        "table_name": "dim_qy_tenant_info_all_d",
                    },
                    distance=0.1,
                    rerank_score=19.0,
                ),
            ],
            metrics=[
                RetrievalHit(
                    document="metric A002",
                    metadata={"asset_type": "metric", "metric_id": "A002"},
                    distance=0.1,
                    rerank_score=18.0,
                )
            ],
        )
        schema_indexes = SchemaIndexLoader().load()

        graph = SchemaGraphBuilder(schema_indexes=schema_indexes).build(context)
        graph_text = format_schema_graph(graph)

        self.assertIn("dm_opt_qy_user_execution_record_all_d", graph.table_names)
        self.assertIn("dim_qy_tenant_info_all_d", graph.table_names)
        self.assertIn("exe_income", graph.field_names)
        self.assertIn("A002", graph.metric_ids)
        self.assertTrue(graph.relations)
        self.assertIn("Table: soyoung_dw.dm_opt_qy_user_execution_record_all_d", graph_text)
        self.assertIn("Field: exe_income", graph_text)
        self.assertIn("Relation:", graph_text)

    def test_city_query_enriches_tenant_dimension_fields(self):
        context = RetrievalContext(
            query="本月北京地区奇迹胶原品项的核销收入",
            fields=[
                RetrievalHit(
                    document="field standard_name",
                    metadata={
                        "asset_type": "field",
                        "field_id": "dm_opt_qy_user_execution_record_all_d.standard_name",
                        "field_name": "standard_name",
                        "table_name": "dm_opt_qy_user_execution_record_all_d",
                    },
                    distance=0.1,
                    rerank_score=20.0,
                ),
            ],
            tables=[
                RetrievalHit(
                    document="table execution",
                    metadata={
                        "asset_type": "table",
                        "table_name": "dm_opt_qy_user_execution_record_all_d",
                        "full_name": "soyoung_dw.dm_opt_qy_user_execution_record_all_d",
                    },
                    distance=0.1,
                    rerank_score=18.0,
                )
            ],
        )
        schema_indexes = SchemaIndexLoader().load()

        graph = SchemaGraphBuilder(schema_indexes=schema_indexes).build(
            context,
            template_id="standard_item_income_top20_30d",
        )
        field_ids = {
            f"{field.get('table_name')}.{field.get('field_name')}"
            for field in graph.fields
        }
        relation_keys = {
            (
                relation.get("source_table"),
                relation.get("source_field"),
                relation.get("target_table"),
                relation.get("target_field"),
            )
            for relation in graph.relations
        }

        self.assertIn("dm_opt_qy_user_execution_record_all_d.tenant_id", field_ids)
        self.assertIn("dim_qy_tenant_info_all_d.city_name", field_ids)
        self.assertIn("dim_qy_tenant_info_all_d.dp", field_ids)
        self.assertIn("dim_qy_tenant_info_all_d", graph.table_names)
        self.assertIn(
            (
                "dm_opt_qy_user_execution_record_all_d",
                "tenant_id",
                "dim_qy_tenant_info_all_d",
                "tenant_id",
            ),
            relation_keys,
        )
        self.assertIn("city_name", graph.schema_graph_text)

    def test_named_item_query_enriches_standard_name_even_without_item_word(self):
        context = RetrievalContext(
            query="本月北京地区奇迹胶原核销收入",
            tables=[
                RetrievalHit(
                    document="table execution",
                    metadata={
                        "asset_type": "table",
                        "table_name": "dm_opt_qy_user_execution_record_all_d",
                        "full_name": "soyoung_dw.dm_opt_qy_user_execution_record_all_d",
                    },
                    distance=0.1,
                    rerank_score=18.0,
                )
            ],
        )
        schema_indexes = SchemaIndexLoader().load()

        graph = SchemaGraphBuilder(schema_indexes=schema_indexes).build(
            context,
            template_id="execution_summary_yesterday",
        )
        field_ids = {
            f"{field.get('table_name')}.{field.get('field_name')}"
            for field in graph.fields
        }

        self.assertIn("dm_opt_qy_user_execution_record_all_d.standard_name", field_ids)


if __name__ == "__main__":
    unittest.main()
