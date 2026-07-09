from app.core.config import settings
from app.intent_router.router import IntentRouter, IntentRouteResult
from app.knowledge_indexer.retrieval_context import RetrievalContext
from app.knowledge_indexer.service import KnowledgeSearchService
from app.llm.local_client import LocalLLMClient
from app.llm.sql_generator import LLMSqlGenerator, LLMSqlResult
from app.llm.sql_safety_gate import SqlSafetyGate, SqlSafetyResult
from app.models.query import (
    LlmSqlResult as LlmSqlResultModel,
    LlmSqlValidation,
    QueryPlan,
    QueryResponse,
    ValidationResult,
)
from app.query_planner.planner import QueryPlanner
from app.schema_graph.graph import SchemaGraph
from app.schema_retrieval.askdata_style_retriever import AskDataStyleSchemaRetriever
from app.sql_generator.generator import SqlGenerator
from app.sql_validator.validator import SqlValidator


# Core 6 queries approved for LLM SQL adoption (gate must pass)
_CORE6_TEMPLATES = {
    "execution_summary_yesterday",
    "store_income_top10_30d",
    "private_new_customer_income_this_week",
    "channel_execution_30d",
    "new_old_customer_execution_30d",
    "revenue_category_execution_30d",
}


class AnswerComposer:
    """组装自然语言取数响应。"""

    def __init__(self):
        self.planner = QueryPlanner()
        self.generator = SqlGenerator()
        self.validator = SqlValidator()
        self.knowledge_search = KnowledgeSearchService()
        self.intent_router = IntentRouter()
        self.schema_retriever = AskDataStyleSchemaRetriever(
            schema_indexes=self.knowledge_search.schema_indexes,
        )
        self.llm_sql_generator = LLMSqlGenerator(
            enabled=settings.llm_enabled,
            model=settings.llm_cot_model,
            timeout_seconds=settings.llm_timeout_seconds,
            client=LocalLLMClient(
                base_url=settings.llm_base_url,
                api_key=settings.llm_api_key,
            ),
        )
        self.sql_safety_gate = SqlSafetyGate()

    def compose(self, question: str) -> QueryResponse:
        retrieval_context = self.knowledge_search.search_structured(question, top_k=20)
        template_id = retrieval_context.top_template_id() or ""
        schema_result = self.schema_retriever.retrieve(retrieval_context, template_id=template_id)
        schema_graph = schema_result["schema_graph"]
        route_result = self.intent_router.route(question, retrieval_context)
        if route_result.intent != "nl2sql":
            return self._compose_explain_response(
                question, retrieval_context, schema_graph,
                route_result, schema_result,
            )

        query_plan = self.planner.plan(
            question,
            retrieval_context=retrieval_context,
            schema_graph=schema_graph,
        )
        template_sql = self.generator.generate(query_plan)
        validation = self.validator.validate(template_sql)

        # --- LLM SQL shadow mode ---
        llm_sql, llm_sql_validation, llm_sql_detail = self._generate_llm_sql(
            query_plan=query_plan,
            schema_graph=schema_graph,
        )

        # Controlled adoption: core 6 queries + gate passed → use LLM SQL
        adopt_llm = (
            template_id in _CORE6_TEMPLATES
            and llm_sql_detail.generated
            and llm_sql_validation.passed
        )
        sql_source = "llm" if adopt_llm else "template"
        final_sql = llm_sql if adopt_llm else template_sql

        return QueryResponse(
            project="Chain-AskData",
            question_summary=f"你想查询：{question}",
            query_plan=query_plan,
            sql=final_sql,
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
            schema_graph=self._schema_graph_payload(schema_result),
            # shadow mode
            template_sql=template_sql,
            llm_sql=llm_sql,
            llm_sql_adopted=adopt_llm,
            llm_sql_validation=llm_sql_validation,
            llm_sql_detail=llm_sql_detail,
            sql_source=sql_source,
        )

    # ------------------------------------------------------------------
    # LLM SQL shadow mode
    # ------------------------------------------------------------------

    def _generate_llm_sql(
        self,
        query_plan: QueryPlan,
        schema_graph: SchemaGraph,
    ) -> tuple[str, LlmSqlValidation, LlmSqlResultModel]:
        result = self.llm_sql_generator.generate(
            cot_steps=query_plan.query_plan_cot,
            schema_graph=schema_graph,
        )
        if not result.generated:
            return "", LlmSqlValidation(), self._to_result_model(result)

        safety = self.sql_safety_gate.validate(result.sql, schema_graph)
        return result.sql, LlmSqlValidation(
            passed=safety.passed,
            errors=safety.errors,
            warnings=safety.warnings,
            used_tables=safety.used_tables,
            used_fields=safety.used_fields,
        ), self._to_result_model(result)

    def _to_result_model(self, result: LLMSqlResult) -> LlmSqlResultModel:
        return LlmSqlResultModel(
            sql=result.sql,
            used_tables=result.used_tables,
            used_fields=result.used_fields,
            explanation=result.explanation,
            generated=result.generated,
            error=result.error,
        )

    # ------------------------------------------------------------------
    # explain / non-nl2sql
    # ------------------------------------------------------------------

    def _compose_explain_response(
        self,
        question: str,
        retrieval_context: RetrievalContext,
        schema_graph: SchemaGraph,
        route_result: IntentRouteResult,
        schema_result: dict,
    ) -> QueryResponse:
        notes = self._build_explain_notes(question, retrieval_context, route_result)
        validation = ValidationResult(
            passed=route_result.intent != "unknown",
            errors=[] if route_result.intent != "unknown" else ["unsupported_intent"],
            warnings=[] if route_result.intent != "unknown" else [route_result.reason],
        )

        return QueryResponse(
            project="Chain-AskData",
            question_summary=f"你想了解：{question}",
            query_plan=QueryPlan(
                intent=route_result.intent,
                business_domain="连锁经管-口径与Schema解释",
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
            schema_graph=self._schema_graph_payload(schema_result),
        )

    def _schema_graph_payload(self, schema_result: dict) -> dict:
        schema_graph = schema_result["schema_graph"]
        payload = schema_graph.to_dict()
        payload.update(
            {
                "retriever": schema_result["retriever"],
                "field_count": schema_result["field_count"],
                "table_count": schema_result["table_count"],
                "metric_count": schema_result["metric_count"],
                "relation_count": schema_result["relation_count"],
            }
        )
        return payload

    def _build_explain_notes(
        self,
        question: str,
        retrieval_context: RetrievalContext,
        route_result: IntentRouteResult,
    ) -> list[str]:
        if route_result.intent == "unknown":
            return self._unknown_notes()

        notes: list[str] = []
        field_notes = self._field_notes(retrieval_context)

        if route_result.intent == "schema_explain":
            notes.extend(field_notes)
            if not notes:
                notes.append("未命中可信字段证据，不建议强行生成 SQL。")
            return notes

        if route_result.intent == "caliber_explain":
            metric_notes = self._metric_caliber_notes(retrieval_context)
            notes.extend(metric_notes)

        question_lower = question.lower()
        if "核销" in question_lower and ("支付" in question_lower or "gmv" in question_lower):
            notes.extend([
                "核销收入：使用 soyoung_dw.dm_opt_qy_user_execution_record_all_d.exe_income，默认按 executed_date 框定核销业务日期。",
                "支付GMV：使用 soyoung_dw.dm_opt_qy_order_info_all_d.pay_gmv，默认按 pay_date 框定支付业务日期，并剔除当日退款。",
                "二者不是同一口径：核销收入偏服务履约/消耗，支付GMV偏收款/交易。",
            ])
        notes.extend(field_notes)
        return notes or [
            "已命中口径解释意图，但当前字段证据不足，不建议强行生成 SQL。"
        ]

    def _unknown_notes(self) -> list[str]:
        return [
            "当前知识库未登记该问题需要的表、字段或指标，不能可靠生成 SQL。",
            (
                "已知支持范围以连锁经管的核销、支付、待核销、门店、品项、"
                "渠道等口径为主。可尝试的问题如：核销收入查询、门店排行、"
                "渠道对比、品项渗透率、支付GMV统计等。"
            ),
        ]

    def _metric_caliber_notes(self, retrieval_context: RetrievalContext) -> list[str]:
        notes: list[str] = []
        seen = set()
        for hit in retrieval_context.metrics[:5]:
            canonical = hit.metadata.get("canonical", "")
            display_name = hit.metadata.get("display_name", "")
            if not canonical or canonical in seen:
                continue
            seen.add(canonical)

            metric = (
                self.planner.metric_registry.get(canonical)
                if hasattr(self.planner, "metric_registry")
                else None
            )
            if metric:
                parts = [f"{metric.display_name}（{canonical}）"]
                if metric.formula:
                    parts.append(f"公式：{metric.formula}")
                notes.append("；".join(parts))
            elif display_name:
                notes.append(
                    f"{display_name}（{canonical}）：口径详情请参见指标定义。"
                )
            else:
                notes.append(f"指标 {canonical}：口径详情请参见指标定义。")
        return notes

    def _field_notes(self, retrieval_context: RetrievalContext) -> list[str]:
        notes = []
        for hit in retrieval_context.fields[:8]:
            field_name = hit.metadata.get("field_name")
            business_name = hit.metadata.get("business_name") or field_name
            full_name = hit.metadata.get("full_name") or field_name
            if field_name:
                notes.append(f"{business_name}：使用 {full_name}")
        return notes

    def _schema_evidence_from_context(self, retrieval_context: RetrievalContext) -> list[str]:
        evidence = []
        for hit in retrieval_context.fields[:8]:
            full_name = hit.metadata.get("full_name")
            business_name = hit.metadata.get("business_name")
            if full_name:
                evidence.append(f"字段证据：{full_name}（{business_name or hit.metadata.get('field_name')}）")
        return evidence
