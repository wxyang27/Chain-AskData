from app.intent_router.router import IntentRouteResult
from app.knowledge_indexer.retrieval_context import RetrievalContext
from app.models.query import (
    LlmSqlResult as LlmSqlResultModel,
    LlmSqlValidation,
    QueryPlan,
    QueryResponse,
    ValidationResult,
)
from app.pipeline.pipeline import AskDataPipeline
from app.schema_graph.graph import SchemaGraph


class AnswerComposer:
    """组装自然语言取数响应。"""

    def __init__(self):
        self.pipeline = AskDataPipeline()
        # Keep metric_registry reference for explain notes
        self.planner = self.pipeline.planner

    def compose(self, question: str) -> QueryResponse:
        result = self.pipeline.run(question)

        # Non-nl2sql path (explain / reject)
        if result.intent_route and result.intent_route.intent != "nl2sql":
            return self._compose_explain_response(
                question,
                result.retrieval_context,
                result.schema_graph,
                result.intent_route,
                result.schema_result,
                pipeline_trace=result.trace.to_dict() if result.trace else {},
            )

        return QueryResponse(
            project="Chain-AskData",
            question_summary=f"你想查询：{question}",
            query_plan=result.query_plan,
            sql=result.final_sql,
            validation=result.validation,
            caliber_notes=[
                "本版本只生成 SQL 与口径说明，不真实执行查询。",
                "核销发生类问题默认使用 executed_date；支付发生类问题默认使用 pay_date。",
                "核销收入使用 exe_income，核销 GMV 使用 exe_amount。",
                "核销客单价默认分母为核销人次 verify_date_id；支付客单价默认分母为支付日期+用户。",
                "门店展示优先使用 sy_hospital_name，主键使用 tenant_id。",
            ] + self._contract_caliber_notes(result.query_plan.semantic_contract),
            retrieval_trace=result.retrieval_context.raw_matches,
            retrieval_context=result.retrieval_context.to_dict(),
            schema_graph=self._schema_graph_payload(result.schema_result),
            # shadow mode
            template_sql=result.template_sql,
            llm_sql=result.llm_sql,
            llm_sql_adopted=result.sql_source == "llm",
            llm_sql_validation=result.llm_sql_validation or LlmSqlValidation(),
            llm_sql_detail=result.llm_sql_detail or LlmSqlResultModel(),
            sql_source=result.sql_source,
            pipeline_trace=result.trace.to_dict() if result.trace else {},
        )


    def _contract_caliber_notes(self, semantic_contract) -> list[str]:
        notes: list[str] = []
        metrics_set = set(semantic_contract.metrics)

        # --- 0元单 ---
        if "zero_income_order_count" in metrics_set:
            notes.append(
                "0元单量 = COUNT(DISTINCT main_order_id) WHERE exe_income = 0；"
                "核销人数使用 COUNT(DISTINCT customer_id)。"
                "0元单判断条件是 exe_income = 0（核销域），不是 pay_gmv = 0（支付域）。"
                "0元核销占比 = COUNT(DISTINCT CASE WHEN exe_income = 0 THEN main_order_id END) "
                "/ NULLIF(COUNT(DISTINCT main_order_id),0)，按门店筛选时用 HAVING 判断阈值。"
            )

        # --- 支付三指标 ---
        has_payment = bool(
            {"payment_gmv", "payment_user_count", "payment_aov_by_user_day"} & metrics_set
        )
        if has_payment:
            notes.append(
                "支付GMV = SUM(pay_gmv)；"
                "支付人数 = COUNT(DISTINCT uid)；"
                "支付客单价 = 支付GMV / NULLIF(支付人次, 0)。"
                "支付域必须过滤 is_paydate_cash = 0（剔除当日退款），"
                "业务日期使用 pay_date。新客支付额外过滤 is_pay_new = 1。"
            )

        # --- 核销人数/人次 ---
        if "execution_user_count" in metrics_set and "execution_visit_count" in metrics_set:
            notes.append(
                "核销人数 = COUNT(DISTINCT customer_id)；"
                "核销人次 = COUNT(DISTINCT verify_date_id)。"
                "二者不能混用：客单价分母是核销人次，渗透率分母是核销人数。"
            )
        elif "execution_visit_count" in metrics_set:
            notes.append(
                "核销人次 = COUNT(DISTINCT verify_date_id)。"
                "涉及新客核销人次占比时，分子为新客核销人次，分母为总核销人次，"
                "并用 NULLIF 防止除零。"
            )

        if "execution_income" in metrics_set and "revenue_category" in semantic_contract.dimensions:
            notes.append(
                "品类/大师团等分类口径使用 revenue_category；"
                "核销收入 = SUM(exe_income)，需要叠加 is_valid = 1 和 executed_date 业务日期。"
            )

        # --- 核销+支付双域 ---
        if "execution_income" in metrics_set and "payment_gmv" in metrics_set:
            notes.append(
                "核销收入使用 executed_date + exe_income + is_valid = 1；"
                "支付GMV使用 pay_date + pay_gmv + is_paydate_cash = 0。"
            )

        return notes


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
        pipeline_trace: dict | None = None,
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
            pipeline_trace=pipeline_trace or {},
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
            if any(term in question for term in ("会员", "membership_level", "L3", "l3")):
                notes.append(
                    "会员等级字段：优先查看 membership_level，可在 "
                    "soyoung_dw.dm_opt_qy_user_summary_info_all_d 或 "
                    "soyoung_dw.dim_user_qy_crm_customer_info_all_d 中取。"
                )
                notes.append(
                    "关联键根据场景使用 crm_customer_id 或 user_id；两张表的 membership_level "
                    "可能存在 bigint/string 类型差异，用户维表为快照口径。"
                )
            if "门店" in question or "机构" in question:
                notes.append("门店名称：优先使用 soyoung_dw.dim_qy_tenant_info_all_d.sy_hospital_name。")
                notes.append("sy_hospital_name（工程主推字段，enricher 会补全）；tenant_alias_name 为兼容字段；hospital_id 不作为展示名称。")
            if "核销人数" in question:
                notes.append("核销人数：使用 soyoung_dw.dm_opt_qy_user_execution_record_all_d.customer_id 去重。")
            notes.extend(field_notes)
            if not notes:
                notes.append("未命中可信字段证据，不建议强行生成 SQL。")
            return notes

        if route_result.intent == "caliber_explain":
            if "核销客单价" in question and "分母" in question:
                notes.append("核销客单价的分母是核销人次：COUNT(DISTINCT verify_date_id)，不是核销人数 customer_id。")
                notes.append("公式使用 SUM(exe_income) / NULLIF(COUNT(DISTINCT verify_date_id),0)；verify_date_id（COUNT DISTINCT）是分母，customer_id；除法必须用 NULLIF 防止除零。")
            if "渗透率" in question and ("品项" in question or "项目" in question):
                notes.append(
                    "品项渗透率 = 品项核销人数 / NULLIF(总核销人数,0)。"
                    "品项匹配使用 standard_name REGEXP/LIKE，人数去重使用 COUNT(DISTINCT customer_id)。"
                )
                notes.append(
                    "计算时必须过滤 is_valid = 1，并用 executed_date 框定核销业务日期；"
                    "不要用 product_id/product_name 替代 standard_name，也不要用核销人次作分母。"
                )
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
