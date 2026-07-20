"""AskDataPipeline: Text2SQL main chain with per-stage observability.

Each stage is a private method that records inputs, outputs, errors,
and latency in a PipelineTrace.  This makes it easy to answer the
interview question "where did the error happen: retrieval, planning,
or SQL generation?"
"""

from time import perf_counter
from typing import Any

from app.core.config import settings
from app.execution.factory import create_sql_executor
from app.execution.objects import SqlExecutionRequest, SqlExecutionResult
from app.feedback.repair_policy import RepairPolicy
from app.feedback.result_validator import ResultValidationResult, ResultValidator
from app.cot_planning.intent_router import IntentRouter, IntentRouteResult
from app.knowledge_indexer.retrieval_context import RetrievalContext
from app.knowledge_indexer.service import KnowledgeSearchService
from app.llm.local_client import LocalLLMClient
from app.sql_generation.llm_generator import LLMSqlGenerator, LLMSqlResult
from app.sql.repairer import StaticSqlRepairer
from app.sql.safety_gate import SqlSafetyGate, SqlSafetyResult
from app.models.query import (
    LlmSqlResult as LlmSqlResultModel,
    LlmSqlValidation,
    QueryPlan,
)
from app.askdata_pipeline.objects import PipelineRunResult, PipelineStageLog, PipelineTrace
from app.cot_planning.planner import QueryPlanner
from app.schema_graph.graph import SchemaGraph
from app.schema_retrieval.askdata_style_retriever import AskDataStyleSchemaRetriever
from app.cot_planning.semantic_contract import SemanticContractBuilder
from app.sql_generation.template_generator import SqlGenerator
from app.sql.validator import SqlValidator


def _now_ms() -> int:
    return int(perf_counter() * 1000)


class AskDataPipeline:
    """Lightweight Pipeline that orchestrates the Text2SQL main chain.

    Each ``_stage_*`` method does one thing, records its work in the
    trace, and returns the result.  Method signatures intentionally use
    ``Any`` where the types are heavyweight Pydantic models to avoid
    import-time coupling.
    """

    def __init__(self):
        # --- services ---
        self.knowledge_search = KnowledgeSearchService()
        self.semantic_contract_builder = SemanticContractBuilder()
        self.schema_retriever = AskDataStyleSchemaRetriever(
            schema_indexes=self.knowledge_search.schema_indexes,
        )
        self.intent_router = IntentRouter()
        self.planner = QueryPlanner()
        self.generator = SqlGenerator()
        self.validator = SqlValidator()

        # --- LLM-dependent services ---
        self.llm_sql_generator = LLMSqlGenerator(
            enabled=settings.llm_enabled,
            model=settings.llm_sql_model,
            timeout_seconds=settings.llm_timeout_seconds,
            client=LocalLLMClient(
                base_url=settings.llm_base_url,
                api_key=settings.llm_api_key,
            ),
        )
        self.sql_safety_gate = SqlSafetyGate()
        self.sql_repairer = StaticSqlRepairer()
        self.result_validator = ResultValidator()
        self.repair_policy = RepairPolicy()

        # --- SQL execution (disabled → mock/sqlite/maxcompute) ---
        self.executor = create_sql_executor()

    # ------------------------------------------------------------------
    # public entry point
    # ------------------------------------------------------------------

    def run(self, question: str) -> PipelineRunResult:
        trace = PipelineTrace(question=question)

        retrieval_context = self._stage_knowledge_retrieval(question, trace)
        semantic_contract = self._stage_semantic_contract(
            question, retrieval_context, trace,
        )
        schema_result, schema_graph = self._stage_schema_retrieval(
            retrieval_context, semantic_contract, trace,
        )
        route_result = self._stage_intent_route(
            question, retrieval_context, semantic_contract, trace,
        )

        if route_result.intent != "nl2sql":
            trace.final_intent = route_result.intent
            return PipelineRunResult(
                question=question,
                retrieval_context=retrieval_context,
                semantic_contract=semantic_contract,
                intent_route=route_result,
                schema_result=schema_result,
                schema_graph=schema_graph,
                trace=trace,
            )

        query_plan = self._stage_query_plan(
            question, retrieval_context, schema_graph, semantic_contract, trace,
        )
        template_sql = self._stage_template_sql(query_plan, schema_graph, trace)
        llm_sql, llm_sql_validation, llm_sql_detail = self._stage_llm_sql(
            query_plan, schema_graph, trace,
        )
        final_sql, sql_source = self._stage_sql_selection(
            template_sql, llm_sql, llm_sql_validation, trace,
        )
        query_plan.llm_adopted = sql_source == "llm"
        query_plan.llm_validation_passed = llm_sql_validation.passed
        query_plan.llm_validation_errors = list(llm_sql_validation.errors)
        if llm_sql and sql_source != "llm":
            query_plan.llm_fallback_reason = "llm_sql_validation_failed"
        self._stage_sql_generation(final_sql, sql_source, template_sql, llm_sql, trace)
        safety_result = self._stage_sql_safety_gate(final_sql, schema_graph, trace)

        # Stage 9: Execute SQL (disabled by default, mock/sqlite for demos)
        execution_result = self._stage_sql_execution(final_sql, trace)
        result_validation = self._stage_result_validation(
            final_sql, query_plan, execution_result, trace,
        )
        (
            final_sql,
            sql_source,
            execution_result,
            result_validation,
            repair_attempt,
        ) = self._stage_repair_attempt(
            final_sql=final_sql,
            sql_source=sql_source,
            template_sql=template_sql,
            query_plan=query_plan,
            schema_graph=schema_graph,
            safety_result=safety_result,
            execution_result=execution_result,
            result_validation=result_validation,
            trace=trace,
        )
        validation = self.validator.validate(final_sql)

        trace.final_sql_source = sql_source
        trace.final_intent = route_result.intent
        trace.final_template_id = query_plan.template_id

        return PipelineRunResult(
            question=question,
            retrieval_context=retrieval_context,
            semantic_contract=semantic_contract,
            intent_route=route_result,
            schema_result=schema_result,
            schema_graph=schema_graph,
            query_plan=query_plan,
            template_sql=template_sql,
            llm_sql=llm_sql,
            final_sql=final_sql,
            sql_source=sql_source,
            validation=validation,
            llm_sql_validation=llm_sql_validation,
            llm_sql_detail=llm_sql_detail,
            template_id=query_plan.template_id,
            trace=trace,
            execution_result=execution_result,
            result_validation=result_validation,
            repair_attempt=repair_attempt,
        )

    # ------------------------------------------------------------------
    # pipeline stages
    # ------------------------------------------------------------------

    def _stage_knowledge_retrieval(
        self, question: str, trace: PipelineTrace,
    ) -> RetrievalContext:
        t0 = _now_ms()
        stage = PipelineStageLog(
            name="knowledge_retrieval",
            inputs={"question": question},
        )
        retrieval_trace_dict = {}
        try:
            ctx, retrieval_trace_dict = self.knowledge_search.search_structured_with_trace(
                question,
                top_k=20,
            )

            stage.outputs = {
                "metric_count": len(ctx.metrics),
                "field_count": len(ctx.fields),
                "table_count": len(ctx.tables),
                "example_count": len(ctx.examples),
                "keyword_hits": retrieval_trace_dict.get("keyword_hit_count", 0),
                "bm25_hits": retrieval_trace_dict.get("bm25_hit_count", 0),
                "vector_hits": retrieval_trace_dict.get("vector_hit_count", 0),
                "rrf_hits": retrieval_trace_dict.get("rrf_hit_count", 0),
                "rerank_hits": retrieval_trace_dict.get("rerank_hit_count", 0),
                "keywords": retrieval_trace_dict.get("keywords", []),
            }
            stage.summary = (
                f"metrics={len(ctx.metrics)} fields={len(ctx.fields)} "
                f"tables={len(ctx.tables)} "
                f"recall=kw:{retrieval_trace_dict.get('keyword_hit_count','?')}/"
                f"bm25:{retrieval_trace_dict.get('bm25_hit_count','?')}/"
                f"vec:{retrieval_trace_dict.get('vector_hit_count','?')}/"
                f"rrf:{retrieval_trace_dict.get('rrf_hit_count','?')}"
            )
        except Exception as exc:
            stage.status = "error"
            stage.errors.append(str(exc))
            ctx = RetrievalContext(query=question)
        stage.latency_ms = _now_ms() - t0
        trace.add_stage(stage)
        return ctx

    def _stage_semantic_contract(
        self,
        question: str,
        retrieval_context: RetrievalContext,
        trace: PipelineTrace,
    ):
        t0 = _now_ms()
        stage = PipelineStageLog(
            name="semantic_contract",
            inputs={"question": question},
        )
        contract = self.semantic_contract_builder.build(question, retrieval_context)
        stage.outputs = {
            "intent": contract.intent,
            "metrics": contract.metrics,
            "dimensions": contract.dimensions,
            "template_id": contract.template_id or "",
        }
        stage.summary = f"intent={contract.intent} metrics={contract.metrics}"
        stage.latency_ms = _now_ms() - t0
        trace.add_stage(stage)
        return contract

    def _stage_schema_retrieval(
        self,
        retrieval_context: RetrievalContext,
        semantic_contract,
        trace: PipelineTrace,
    ) -> tuple[dict[str, Any], SchemaGraph]:
        t0 = _now_ms()
        template_id = (
            semantic_contract.template_id
            or retrieval_context.top_template_id()
            or self.planner._match_case(
                retrieval_context.query, retrieval_context,
            )["template_id"]
        )
        stage = PipelineStageLog(
            name="schema_retrieval",
            inputs={"template_id": template_id},
        )
        schema_result = self.schema_retriever.retrieve(
            retrieval_context, template_id=template_id,
        )
        sg = schema_result["schema_graph"]
        stage.outputs = {
            "field_count": schema_result.get("field_count", 0),
            "table_count": schema_result.get("table_count", 0),
            "metric_count": schema_result.get("metric_count", 0),
            "relation_count": schema_result.get("relation_count", 0),
        }
        stage.summary = f"fields={stage.outputs['field_count']} tables={stage.outputs['table_count']}"
        stage.latency_ms = _now_ms() - t0
        trace.add_stage(stage)
        return schema_result, sg

    def _stage_intent_route(
        self,
        question: str,
        retrieval_context: RetrievalContext,
        semantic_contract,
        trace: PipelineTrace,
    ) -> IntentRouteResult:
        t0 = _now_ms()
        stage = PipelineStageLog(
            name="intent_route",
            inputs={"question": question},
        )
        route = self.intent_router.route(question, retrieval_context)
        # Semantic contract may override
        if semantic_contract.intent != route.intent and semantic_contract.intent != "nl2sql":
            route = IntentRouteResult(
                intent=semantic_contract.intent,
                confidence=0.95,
                reason=semantic_contract.reject_reason or "semantic override",
                evidence=semantic_contract.required_fields + semantic_contract.metrics,
            )
        stage.outputs = {"intent": route.intent, "confidence": route.confidence}
        stage.summary = f"intent={route.intent}"
        stage.latency_ms = _now_ms() - t0
        trace.add_stage(stage)
        return route

    def _stage_query_plan(
        self,
        question: str,
        retrieval_context: RetrievalContext,
        schema_graph: SchemaGraph,
        semantic_contract,
        trace: PipelineTrace,
    ) -> QueryPlan:
        t0 = _now_ms()
        stage = PipelineStageLog(
            name="query_plan",
            inputs={"question": question},
        )
        plan = self.planner.plan(
            question,
            retrieval_context=retrieval_context,
            schema_graph=schema_graph,
            semantic_contract=semantic_contract,
        )
        stage.outputs = {
            "intent": plan.intent,
            "template_id": plan.template_id,
            "sql_strategy": plan.sql_strategy,
            "metrics": [m.canonical for m in plan.metrics],
            "llm_adopted": plan.llm_adopted,
            "llm_model": plan.llm_model,
        }
        stage.summary = f"strategy={plan.sql_strategy} metrics={stage.outputs['metrics']}"
        stage.latency_ms = _now_ms() - t0
        trace.add_stage(stage)
        return plan

    def _stage_template_sql(
        self,
        query_plan: QueryPlan,
        schema_graph: SchemaGraph,
        trace: PipelineTrace,
    ) -> str:
        t0 = _now_ms()
        stage = PipelineStageLog(
            name="template_sql",
            inputs={"template_id": query_plan.template_id},
        )
        sql = self.generator.generate(query_plan)
        # Apply static repair to template SQL
        repair = self.sql_repairer.repair(
            sql=sql,
            semantic_contract=query_plan.semantic_contract,
            schema_graph=schema_graph,
            errors=[],
        )
        if repair.repaired:
            safety = self.sql_safety_gate.validate(repair.sql, schema_graph)
            if safety.passed:
                sql = repair.sql
                stage.outputs["repair"] = True
                stage.outputs["fixes"] = repair.fixes
        stage.outputs["length"] = len(sql)
        stage.summary = f"template={query_plan.template_id} length={len(sql)}"
        stage.latency_ms = _now_ms() - t0
        trace.add_stage(stage)
        return sql

    def _stage_llm_sql(
        self,
        query_plan: QueryPlan,
        schema_graph: SchemaGraph,
        trace: PipelineTrace,
    ) -> tuple[str, LlmSqlValidation, LlmSqlResultModel]:
        t0 = _now_ms()
        stage = PipelineStageLog(
            name="llm_sql",
            inputs={
                "llm_enabled": self.llm_sql_generator.enabled,
                "model": self.llm_sql_generator.model,
            },
        )
        result = self.llm_sql_generator.generate(
            cot_steps=query_plan.query_plan_cot,
            schema_graph=schema_graph,
        )
        validation = LlmSqlValidation()
        if result.generated:
            safety = self.sql_safety_gate.validate(result.sql, schema_graph)
            if not safety.passed:
                repair = self.sql_repairer.repair(
                    sql=result.sql,
                    semantic_contract=query_plan.semantic_contract,
                    schema_graph=schema_graph,
                    errors=safety.errors,
                )
                if repair.repaired:
                    repaired_safety = self.sql_safety_gate.validate(
                        repair.sql, schema_graph,
                    )
                    if repaired_safety.passed:
                        result.sql = repair.sql
                        safety = repaired_safety
                    else:
                        safety.errors.extend(
                            f"repair_failed:{e}" for e in repaired_safety.errors
                        )
            validation = LlmSqlValidation(
                passed=safety.passed,
                errors=safety.errors,
                warnings=safety.warnings,
                used_tables=safety.used_tables,
                used_fields=safety.used_fields,
            )
            stage.outputs = {
                "generated": True,
                "gate_passed": validation.passed,
                "length": len(result.sql),
                "model": self.llm_sql_generator.model,
            }
            stage.summary = f"generated={result.generated} gate_passed={validation.passed}"
        else:
            stage.outputs = {"generated": False, "error": result.error}
            stage.summary = f"generated=False error={result.error}"
            stage.status = "warning"

        if validation.errors:
            stage.errors = list(validation.errors)

        stage.latency_ms = _now_ms() - t0
        trace.add_stage(stage)
        return result.sql, validation, self._to_result_model(result)

    def _stage_sql_selection(
        self,
        template_sql: str,
        llm_sql: str,
        llm_sql_validation: LlmSqlValidation,
        trace: PipelineTrace,
    ) -> tuple[str, str]:
        t0 = _now_ms()
        adopt_llm = bool(llm_sql and llm_sql_validation.passed)
        sql_source = "llm" if adopt_llm else "template"
        final_sql = llm_sql if adopt_llm else template_sql

        stage = PipelineStageLog(
            name="sql_selection",
            inputs={"adopt_llm": adopt_llm},
            outputs={"sql_source": sql_source, "length": len(final_sql)},
            summary=f"source={sql_source}",
        )
        stage.latency_ms = _now_ms() - t0
        trace.add_stage(stage)
        return final_sql, sql_source

    def _stage_sql_generation(
        self,
        final_sql: str,
        sql_source: str,
        template_sql: str,
        llm_sql: str,
        trace: PipelineTrace,
    ) -> None:
        t0 = _now_ms()
        stage = PipelineStageLog(
            name="sql_generation",
            inputs={
                "sql_source": sql_source,
                "has_template_sql": bool(template_sql),
                "has_llm_sql": bool(llm_sql),
            },
            outputs={
                "final_length": len(final_sql),
                "template_length": len(template_sql),
                "llm_length": len(llm_sql),
            },
            summary=f"source={sql_source} length={len(final_sql)}",
        )
        stage.latency_ms = _now_ms() - t0
        trace.add_stage(stage)

    def _stage_sql_safety_gate(
        self,
        sql: str,
        schema_graph: SchemaGraph,
        trace: PipelineTrace,
    ) -> SqlSafetyResult:
        t0 = _now_ms()
        stage = PipelineStageLog(name="sql_safety_gate")
        result = self.sql_safety_gate.validate(sql, schema_graph)
        stage.outputs = {
            "passed": result.passed,
            "error_count": len(result.errors),
            "warning_count": len(result.warnings),
            "used_tables": result.used_tables,
            "used_fields": result.used_fields,
        }
        if not result.passed:
            stage.status = "warning"
            stage.errors = list(result.errors)
        stage.summary = f"passed={result.passed} errors={len(result.errors)}"
        stage.latency_ms = _now_ms() - t0
        trace.add_stage(stage)
        return result

    def _stage_sql_execution(
        self, sql: str, trace: PipelineTrace,
    ) -> SqlExecutionResult:
        t0 = _now_ms()
        stage = PipelineStageLog(
            name="execution",
            inputs={
                "mode": self.executor.mode,
                "enabled": self.executor.enabled,
            },
        )
        request = SqlExecutionRequest(
            sql=sql,
            mode=self.executor.mode,
            timeout_seconds=settings.execution_timeout_seconds,
            max_rows=settings.execution_max_rows,
        )
        result = self.executor.execute(request)
        stage.outputs = {
            "enabled": result.enabled,
            "mode": result.mode,
            "status": result.status,
            "dry_run": result.dry_run,
            "columns": result.columns,
            "row_count": result.row_count,
            "sample_row_count": len(result.sample_rows),
        }
        if result.error:
            stage.errors.append(result.error)
        if result.status == "skipped":
            stage.status = "skipped"
        elif result.status != "success":
            stage.status = "warning" if result.dry_run else "error"

        stage.summary = (
            f"mode={result.mode} status={result.status} dry_run={result.dry_run} "
            f"cols={len(result.columns)} rows={result.row_count}"
        )
        stage.latency_ms = _now_ms() - t0
        trace.add_stage(stage)
        return result

    def _stage_result_validation(
        self,
        sql: str,
        query_plan: QueryPlan,
        execution_result: SqlExecutionResult,
        trace: PipelineTrace,
    ) -> ResultValidationResult:
        t0 = _now_ms()
        stage = PipelineStageLog(name="result_validation")
        result = self.result_validator.validate(
            sql=sql,
            query_plan=query_plan,
            execution_result=execution_result,
        )
        stage.outputs = {
            "passed": result.passed,
            "status": result.status,
            "error_count": len(result.errors),
            "warning_count": len(result.warnings),
            "expected_columns": result.expected_columns,
            "actual_columns": result.actual_columns,
        }
        if result.status == "skipped":
            stage.status = "skipped"
        elif not result.passed:
            stage.status = "warning"
            stage.errors = list(result.errors)
        stage.summary = f"status={result.status} passed={result.passed}"
        stage.latency_ms = _now_ms() - t0
        trace.add_stage(stage)
        return result

    def _stage_repair_attempt(
        self,
        *,
        final_sql: str,
        sql_source: str,
        template_sql: str,
        query_plan: QueryPlan,
        schema_graph: SchemaGraph,
        safety_result: SqlSafetyResult,
        execution_result: SqlExecutionResult,
        result_validation: ResultValidationResult,
        trace: PipelineTrace,
    ) -> tuple[str, str, SqlExecutionResult, ResultValidationResult, dict[str, Any]]:
        t0 = _now_ms()
        stage = PipelineStageLog(name="repair_attempt")
        safety_errors = [] if safety_result.passed else list(safety_result.errors)

        # Default disabled mode should stay quiet: no execution feedback exists.
        if result_validation.status == "skipped" and sql_source == "template":
            payload = {
                "attempted": False,
                "reason": "execution_skipped",
                "advice": {"needed": False, "reason": "execution_skipped"},
            }
            stage.outputs = payload
            stage.status = "skipped"
            stage.summary = "skipped: execution disabled"
            stage.latency_ms = _now_ms() - t0
            trace.add_stage(stage)
            return final_sql, sql_source, execution_result, result_validation, payload

        advice = self.repair_policy.advise(
            execution_result=execution_result,
            result_validation=result_validation,
            safety_errors=safety_errors,
            sql_source=sql_source,
        )
        payload: dict[str, Any] = {
            "attempted": False,
            "advice": advice.to_dict(),
            "repair_adopted": False,
            "fallback_used": False,
            "final_sql_source": sql_source,
        }
        if not advice.needed:
            stage.outputs = payload
            stage.summary = "no repair needed"
            stage.latency_ms = _now_ms() - t0
            trace.add_stage(stage)
            return final_sql, sql_source, execution_result, result_validation, payload

        payload["attempted"] = True
        repair = self.sql_repairer.repair(
            sql=final_sql,
            semantic_contract=query_plan.semantic_contract,
            schema_graph=schema_graph,
            errors=safety_errors + result_validation.errors + ([execution_result.error] if execution_result.error else []),
        )
        payload["static_repair"] = {
            "repaired": repair.repaired,
            "fixes": repair.fixes,
        }

        if repair.repaired:
            repaired_safety = self.sql_safety_gate.validate(repair.sql, schema_graph)
            payload["repaired_safety"] = {
                "passed": repaired_safety.passed,
                "errors": repaired_safety.errors,
            }
            if repaired_safety.passed:
                repaired_execution = self._execute_sql(repair.sql)
                repaired_validation = self.result_validator.validate(
                    sql=repair.sql,
                    query_plan=query_plan,
                    execution_result=repaired_execution,
                )
                payload["repaired_result_validation"] = repaired_validation.to_dict()
                if repaired_validation.passed:
                    payload["repair_adopted"] = True
                    repaired_source = f"{sql_source}_repaired"
                    payload["final_sql_source"] = repaired_source
                    stage.outputs = payload
                    stage.summary = f"adopted static repair: {repair.fixes}"
                    stage.latency_ms = _now_ms() - t0
                    trace.add_stage(stage)
                    return repair.sql, repaired_source, repaired_execution, repaired_validation, payload

        if sql_source != "template" and template_sql:
            fallback_execution = self._execute_sql(template_sql)
            fallback_validation = self.result_validator.validate(
                sql=template_sql,
                query_plan=query_plan,
                execution_result=fallback_execution,
            )
            payload["fallback_used"] = True
            payload["fallback_result_validation"] = fallback_validation.to_dict()
            payload["final_sql_source"] = "template_fallback"
            stage.outputs = payload
            stage.status = "warning"
            stage.summary = "fallback to template SQL"
            stage.latency_ms = _now_ms() - t0
            trace.add_stage(stage)
            return template_sql, "template_fallback", fallback_execution, fallback_validation, payload

        payload["final_sql_source"] = sql_source
        stage.outputs = payload
        stage.status = "warning"
        stage.errors = result_validation.errors + safety_errors
        stage.summary = "repair unavailable; keep current SQL"
        stage.latency_ms = _now_ms() - t0
        trace.add_stage(stage)
        return final_sql, sql_source, execution_result, result_validation, payload

    def _execute_sql(self, sql: str) -> SqlExecutionResult:
        request = SqlExecutionRequest(
            sql=sql,
            mode=self.executor.mode,
            timeout_seconds=settings.execution_timeout_seconds,
            max_rows=settings.execution_max_rows,
        )
        return self.executor.execute(request)

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _to_result_model(self, result: LLMSqlResult) -> LlmSqlResultModel:
        return LlmSqlResultModel(
            sql=result.sql,
            used_tables=result.used_tables,
            used_fields=result.used_fields,
            explanation=result.explanation,
            generated=result.generated,
            error=result.error,
        )
