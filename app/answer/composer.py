from app.knowledge_indexer.service import KnowledgeSearchService
from app.intent_router.router import IntentRouter, IntentRouteResult
from app.knowledge_indexer.retrieval_context import RetrievalContext
from app.models.query import QueryPlan, QueryResponse, ValidationResult
from app.query_planner.planner import QueryPlanner
from app.schema_graph.builder import SchemaGraphBuilder
from app.schema_graph.graph import SchemaGraph
from app.sql_generator.generator import SqlGenerator
from app.sql_validator.validator import SqlValidator


class AnswerComposer:
    """组装自然语言取数响应。"""

    def __init__(self):
        self.planner = QueryPlanner()
        self.generator = SqlGenerator()
        self.validator = SqlValidator()
        self.knowledge_search = KnowledgeSearchService()
        self.intent_router = IntentRouter()
        self.schema_graph_builder = SchemaGraphBuilder()

    def compose(self, question: str) -> QueryResponse:
        retrieval_context = self.knowledge_search.search_structured(question, top_k=10)
        schema_graph = self.schema_graph_builder.build(retrieval_context)
        route_result = self.intent_router.route(question, retrieval_context)
        if route_result.intent != "nl2sql":
            return self._compose_explain_response(question, retrieval_context, schema_graph, route_result)

        query_plan = self.planner.plan(
            question,
            retrieval_context=retrieval_context,
            schema_graph=schema_graph,
        )
        sql = self.generator.generate(query_plan)
        validation = self.validator.validate(sql)

        return QueryResponse(
            project="Chain-AskData",
            question_summary=f"你想查询：{question}",
            query_plan=query_plan,
            sql=sql,
            validation=validation,
            caliber_notes=[
                "本版本只生成 SQL 与口径说明，不真实执行查询。",
                "核销发生类问题默认使用 executed_date；支付发生类问题默认使用 pay_date。",
                "核销收入使用 exe_income，核销 GMV 使用 exe_amount。",
                "核销客单价默认分母为核销人次 verify_date_id；支付客单价默认分母为支付日期+用户。",
                "门店展示优先使用 sy_hospital_name，主键使用 tenant_id。",
            ],
            retrieval_trace=retrieval_context.raw_matches,
            retrieval_context=retrieval_context.to_dict(),
            schema_graph=schema_graph.to_dict(),
        )

    def _compose_explain_response(
        self,
        question: str,
        retrieval_context: RetrievalContext,
        schema_graph: SchemaGraph,
        route_result: IntentRouteResult,
    ) -> QueryResponse:
        notes = self._build_explain_notes(question, retrieval_context, route_result)
        validation = ValidationResult(
            passed=route_result.intent != "unknown",
            errors=[] if route_result.intent != "unknown" else ["unsupported_intent"],
            warnings=[] if route_result.intent != "unknown" else [route_result.reason],
        )

        return QueryResponse(
            project="Chain-AskData",
            question_summary=f"\u4f60\u60f3\u4e86\u89e3\uff1a{question}",
            query_plan=QueryPlan(
                intent=route_result.intent,
                business_domain="\u8fde\u9501\u7ecf\u7ba1-\u53e3\u5f84\u4e0eSchema\u89e3\u91ca",
                original_question=question,
                sql_strategy="explain_only",
                metrics=[],
                source_tables=retrieval_context.top_table_names(limit=5),
                risk_flags=retrieval_context.risks,
                retrieved_metric_ids=retrieval_context.top_metric_ids(limit=5),
                retrieved_field_names=retrieval_context.top_field_names(limit=8),
                retrieved_table_names=retrieval_context.top_table_names(limit=5),
                retrieved_example_ids=retrieval_context.top_example_ids(limit=3),
                planning_evidence=[route_result.reason],
                schema_evidence=self._schema_evidence_from_context(retrieval_context),
            ),
            sql="",
            validation=validation,
            caliber_notes=notes,
            retrieval_trace=retrieval_context.raw_matches,
            retrieval_context=retrieval_context.to_dict(),
            schema_graph=schema_graph.to_dict(),
        )

    def _build_explain_notes(
        self,
        question: str,
        retrieval_context: RetrievalContext,
        route_result: IntentRouteResult,
    ) -> list[str]:
        if route_result.intent == "unknown":
            return [
                "\u5f53\u524d\u77e5\u8bc6\u5e93\u672a\u767b\u8bb0\u8be5\u95ee\u9898\u9700\u8981\u7684\u8868\u3001\u5b57\u6bb5\u6216\u6307\u6807\uff0c\u4e0d\u80fd\u53ef\u9760\u751f\u6210 SQL\u3002",
                "\u5df2\u77e5\u652f\u6301\u8303\u56f4\u4ee5\u8fde\u9501\u7ecf\u7ba1\u7684\u6838\u9500\u3001\u652f\u4ed8\u3001\u5f85\u6838\u9500\u3001\u95e8\u5e97\u3001\u54c1\u9879\u3001\u6e20\u9053\u7b49\u53e3\u5f84\u4e3a\u4e3b\u3002",
            ]

        notes = []
        field_notes = self._field_notes(retrieval_context)
        if route_result.intent == "schema_explain":
            notes.extend(field_notes)
            if not notes:
                notes.append("\u672a\u547d\u4e2d\u53ef\u4fe1\u5b57\u6bb5\u8bc1\u636e\uff0c\u4e0d\u5efa\u8bae\u5f3a\u884c\u751f\u6210 SQL\u3002")
            return notes

        question_lower = question.lower()
        if "\u6838\u9500" in question_lower and ("\u652f\u4ed8" in question_lower or "gmv" in question_lower):
            notes.extend([
                "\u6838\u9500\u6536\u5165\uff1a\u4f7f\u7528 soyoung_dw.dm_opt_qy_user_execution_record_all_d.exe_income\uff0c\u9ed8\u8ba4\u6309 executed_date \u6846\u5b9a\u6838\u9500\u4e1a\u52a1\u65e5\u671f\u3002",
                "\u652f\u4ed8GMV\uff1a\u4f7f\u7528 soyoung_dw.dm_opt_qy_order_info_all_d.pay_gmv\uff0c\u9ed8\u8ba4\u6309 pay_date \u6846\u5b9a\u652f\u4ed8\u4e1a\u52a1\u65e5\u671f\uff0c\u5e76\u5254\u9664\u5f53\u65e5\u9000\u6b3e\u3002",
                "\u4e8c\u8005\u4e0d\u662f\u540c\u4e00\u53e3\u5f84\uff1a\u6838\u9500\u6536\u5165\u504f\u670d\u52a1\u5c65\u7ea6/\u6d88\u8017\uff0c\u652f\u4ed8GMV\u504f\u6536\u6b3e/\u4ea4\u6613\u3002",
            ])
        notes.extend(field_notes)
        return notes or ["\u5df2\u547d\u4e2d\u53e3\u5f84\u89e3\u91ca\u610f\u56fe\uff0c\u4f46\u5f53\u524d\u5b57\u6bb5\u8bc1\u636e\u4e0d\u8db3\uff0c\u4e0d\u5efa\u8bae\u5f3a\u884c\u751f\u6210 SQL\u3002"]

    def _field_notes(self, retrieval_context: RetrievalContext) -> list[str]:
        notes = []
        for hit in retrieval_context.fields[:8]:
            field_name = hit.metadata.get("field_name")
            business_name = hit.metadata.get("business_name") or field_name
            full_name = hit.metadata.get("full_name") or field_name
            if field_name:
                notes.append(f"{business_name}\uff1a\u4f7f\u7528 {full_name}")
        return notes

    def _schema_evidence_from_context(self, retrieval_context: RetrievalContext) -> list[str]:
        evidence = []
        for hit in retrieval_context.fields[:8]:
            full_name = hit.metadata.get("full_name")
            business_name = hit.metadata.get("business_name")
            if full_name:
                evidence.append(f"\u5b57\u6bb5\u8bc1\u636e\uff1a{full_name}\uff08{business_name or hit.metadata.get('field_name')}\uff09")
        return evidence
