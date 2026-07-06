from app.metric_registry.registry import MetricRegistry
from app.models.query import DimensionPlan, QueryPlan
from app.schema_retrieval.retriever import SchemaRetriever


class QueryPlanner:
    """自然语言到 QueryPlan 的最小规划器。"""

    def __init__(self):
        self.metric_registry = MetricRegistry()
        self.schema_retriever = SchemaRetriever()

    def plan(self, question: str) -> QueryPlan:
        metric = self.metric_registry.get_store_income_metric()
        source_tables = self.schema_retriever.retrieve_for_store_income()

        return QueryPlan(
            intent="nl2sql",
            business_domain="门店核销经营",
            metrics=[metric],
            dimensions=[
                DimensionPlan(
                    field="sy_hospital_name",
                    alias="门店",
                    source_table="dim_qy_tenant_info_all_d",
                )
            ],
            filters=[
                "a.dp = DATE_SUB(CURRENT_DATE(),1)",
                "a.is_valid = 1",
                "a.executed_date BETWEEN DATE_SUB(CURRENT_DATE(),30) AND DATE_SUB(CURRENT_DATE(),1)",
            ],
            source_tables=source_tables,
            risk_flags=[
                "核销收入使用 exe_income",
                "门店展示优先使用 sy_hospital_name",
                "ORDER BY 必须带 LIMIT",
            ],
        )
