from app.assets.loader import load_yaml_asset
from app.business.item_progress import (
    ITEM_INCOME_PROGRESS_METRIC,
    ITEM_INCOME_PROGRESS_TEMPLATE,
    extract_item_name,
    is_item_income_progress_question,
)
from app.core.config import settings
from app.knowledge_indexer.retrieval_context import RetrievalContext
from app.llm.local_client import LocalLLMClient
from app.cot_planning.query_plan_cot_generator import LLMQueryPlanCoTGenerator
from app.metric_registry.registry import MetricRegistry
from app.models.query import CoTSemantics, DimensionPlan, QueryPlan, QueryPlanCoT, SemanticContract
from app.schema_retrieval.retriever import SchemaRetriever
from app.schema_graph.graph import SchemaGraph


class QueryPlanner:
    """自然语言到 QueryPlan 的确定性规划器。

    MVP 阶段仍采用 template-first 路线，但会消费 RetrievalContext，把 RAG 命中的
    指标、字段、表、样例和风险写回 QueryPlan，便于解释和后续 SQL 生成。
    """

    def __init__(self, llm_cot_generator: LLMQueryPlanCoTGenerator | None = None):
        self.metric_registry = MetricRegistry()
        self.schema_retriever = SchemaRetriever()
        self.demo_cases = load_yaml_asset("knowledge/examples/demo_queries.json")
        self.cases_by_template = {
            case["template_id"]: case
            for case in self.demo_cases
        }
        self.llm_cot_generator = llm_cot_generator or LLMQueryPlanCoTGenerator(
            enabled=settings.llm_enabled,
            model=settings.llm_cot_model,
            timeout_seconds=settings.llm_timeout_seconds,
            client=LocalLLMClient(
                base_url=settings.llm_base_url,
                api_key=settings.llm_api_key,
            ),
        )

    def plan(
        self,
        question: str,
        retrieval_context: RetrievalContext | None = None,
        schema_graph: SchemaGraph | None = None,
        semantic_contract: SemanticContract | None = None,
    ) -> QueryPlan:
        # Template is always available as fallback
        demo_case = self._match_case(question, retrieval_context, semantic_contract)
        retrieved_metric_ids = retrieval_context.top_metric_ids() if retrieval_context else []
        retrieved_field_names = retrieval_context.top_field_names() if retrieval_context else []
        retrieved_table_names = retrieval_context.top_table_names() if retrieval_context else []
        retrieved_example_ids = retrieval_context.top_example_ids() if retrieval_context else []
        planning_evidence = self._build_planning_evidence(demo_case, retrieval_context)
        schema_evidence = self._build_schema_evidence(retrieval_context)
        rule_query_plan_cot = self._build_query_plan_cot(
            demo_case=demo_case,
            retrieval_context=retrieval_context,
            schema_graph=schema_graph,
        )

        # LLM is the primary source; template is fallback
        llm_cot_result = self.llm_cot_generator.generate(
            question=question,
            schema_graph=schema_graph,
            fallback_steps=rule_query_plan_cot,
        )
        query_plan_cot = (
            llm_cot_result.steps
            if llm_cot_result.adopted
            else rule_query_plan_cot
        )
        query_plan_cot = self._postprocess_query_plan_cot(question, query_plan_cot)

        # --- Build QueryPlan: LLM query_semantics primary, template fallback ---
        semantics = (
            query_plan_cot[0].query_semantics
            if llm_cot_result.adopted and query_plan_cot
            else None
        )

        if semantics and semantics.metrics:
            # LLM primary path
            semantic_metrics = self._merge_contract_values(
                semantics.metrics,
                semantic_contract.metrics if semantic_contract else [],
            )
            metrics = self.metric_registry.get_many(semantic_metrics)
            time_range = self._semantics_time_label(semantics.time_type)
            dimensions = [
                DimensionPlan(field=dim, alias=dim, source_table="")
                for dim in self._merge_contract_values(
                    semantics.dimensions,
                    semantic_contract.dimensions if semantic_contract else [],
                )
            ]
            filters = self._merge_contract_values(
                semantics.filters,
                semantic_contract.filters if semantic_contract else [],
            )
            sql_strategy = "llm_primary"
            planning_evidence.insert(0, "LLM 语义理解：主链路")
        else:
            # Template fallback path
            metric_ids = self._merge_contract_values(
                demo_case["metrics"],
                semantic_contract.metrics if semantic_contract else [],
            )
            metrics = self.metric_registry.get_many(metric_ids)
            time_range = (
                "本月MTD（自然月1日至昨天）"
                if self._question_requests_this_month_mtd(question)
                else self._infer_time_range(demo_case["template_id"])
            )
            dimensions = [
                DimensionPlan(**dimension)
                for dimension in demo_case.get("dimensions", [])
            ]
            filters = self._merge_contract_values(
                self._infer_filters(demo_case["template_id"]),
                semantic_contract.filters if semantic_contract else [],
            )
            sql_strategy = "template_fallback"

        risk_flags = demo_case.get("risk_flags", []).copy()
        if retrieval_context:
            risk_flags.extend(flag for flag in retrieval_context.risks if flag not in risk_flags)

        source_tables = self.schema_retriever.retrieve(demo_case["source_tables"])
        source_tables = self._merge_retrieved_tables(source_tables, retrieval_context)

        return QueryPlan(
            intent="nl2sql",
            business_domain=demo_case["business_domain"],
            original_question=question,
            case_id=demo_case["case_id"],
            template_id=demo_case["template_id"],
            sql_strategy=sql_strategy,
            time_range=time_range,
            metrics=metrics,
            dimensions=dimensions,
            filters=filters,
            source_tables=source_tables,
            risk_flags=risk_flags,
            retrieved_metric_ids=retrieved_metric_ids,
            retrieved_field_names=retrieved_field_names,
            retrieved_table_names=retrieved_table_names,
            retrieved_example_ids=retrieved_example_ids,
            planning_evidence=planning_evidence,
            schema_evidence=schema_evidence,
            query_plan_cot=query_plan_cot,
            llm_enabled=llm_cot_result.enabled,
            llm_adopted=llm_cot_result.adopted,
            llm_model=llm_cot_result.model,
            llm_fallback_reason=llm_cot_result.fallback_reason,
            llm_validation_passed=llm_cot_result.validation_passed,
            llm_validation_errors=llm_cot_result.validation_errors,
            llm_latency_ms=llm_cot_result.latency_ms,
            llm_repair_count=llm_cot_result.repair_count,
            semantic_contract=semantic_contract or SemanticContract(),
        )

    def _postprocess_query_plan_cot(
        self,
        question: str,
        steps: list[QueryPlanCoT],
    ) -> list[QueryPlanCoT]:
        """Normalize semantics that are commonly drifted by examples."""
        cleaned_steps: list[QueryPlanCoT] = []
        for step in steps:
            semantics = step.query_semantics or CoTSemantics()
            dimensions = list(semantics.dimensions)
            instructions = list(step.operation_instructions)
            output_target = step.output_target
            semantic_updates: dict[str, object] = {}

            if self._question_requests_this_month_mtd(question):
                semantic_updates["time_type"] = "this_month_mtd"
                instructions = self._remove_rolling_30d_time_instructions(instructions)
                instructions.append(
                    "时间口径：本月=自然月MTD，业务日期 >= DATETRUNC(CURRENT_DATE(), 'MONTH') 且 <= DATE_SUB(CURRENT_DATE(), 1)，不得按最近30天处理"
                )

            if not self._question_requests_store_breakdown(question):
                dimensions = [
                    dim for dim in dimensions
                    if dim not in {"\u95e8\u5e97", "\u673a\u6784", "\u533b\u9662", "tenant_id", "sy_hospital_name"}
                ]
                before_count = len(instructions)
                instructions = [
                    instruction
                    for instruction in instructions
                    if not self._looks_like_store_grouping_instruction(instruction)
                ]

                if self._contains_store_output(output_target):
                    output_target = "\u54c1\u9879\u3001\u6838\u9500\u6536\u5165" if "\u54c1\u9879" in question else "\u6838\u9500\u6536\u5165"

                if len(instructions) != before_count:
                    instructions.append(
                        "\u6700\u540e\u6c47\u603b\uff1a\u4e0d\u505a\u989d\u5916\u7ef4\u5ea6\u5206\u7ec4\uff0c\u6309\u95ee\u9898\u8981\u6c42\u8fd4\u56de\u6838\u9500\u6536\u5165"
                    )

            for requested_dimension in self._requested_group_dimensions(question):
                if requested_dimension not in dimensions:
                    dimensions.append(requested_dimension)

            metrics = self._augment_metrics_from_question(question, list(semantics.metrics))
            if metrics != list(semantics.metrics):
                semantic_updates["metrics"] = metrics

            if self._question_requests_named_channel_set(question):
                channel_filter_instruction = (
                    "渠道口径：问题点名私域/公域/老带新对比时，"
                    "必须加 cx_first_channel IN ('私域','公域','老带新')，"
                    "不得只 GROUP BY 全部渠道"
                )
                if channel_filter_instruction not in instructions:
                    instructions.append(channel_filter_instruction)

            item_name = self._named_item_filter_value(question)
            if item_name:
                item_filter_instruction = (
                    f"品项口径：问题点名{item_name}时，"
                    f"必须加 standard_name = '{item_name}' 或 standard_name REGEXP '{item_name}'"
                )
                if item_filter_instruction not in instructions:
                    instructions.append(item_filter_instruction)

            semantic_updates["dimensions"] = dimensions
            cleaned_steps.append(
                step.model_copy(
                    update={
                        "operation_instructions": instructions,
                        "output_target": output_target,
                        "query_semantics": semantics.model_copy(
                            update=semantic_updates
                        ),
                    }
                )
            )
        return cleaned_steps

    def _augment_metrics_from_question(self, question: str, metrics: list[str]) -> list[str]:
        augmented = list(dict.fromkeys(metrics))

        def add(metric: str) -> None:
            if metric not in augmented:
                augmented.append(metric)

        payment_context = any(term in question for term in ("支付", "付了", "付的", "GMV"))
        if "待核销" in question or "没核销" in question:
            add("unverified_amount")
        if "渗透率" in question:
            add("standard_item_penetration")
        if "0元单" in question or "0 元单" in question:
            add("zero_income_order_count")

        if is_item_income_progress_question(question):
            add(ITEM_INCOME_PROGRESS_METRIC)

        if payment_context and any(term in question for term in ("支付", "付了", "GMV")):
            add("payment_gmv")
        if payment_context and any(term in question for term in ("支付人数", "多少人付", "付的人")):
            add("payment_user_count")
        if payment_context and any(term in question for term in ("客单价", "人均")):
            add("payment_aov_by_user_day")

        execution_income_terms = (
            "核销收入",
            "核销了多少钱",
            "核销金额",
            "消耗金额",
            "业绩",
            "成交后收入",
        )
        if any(term in question for term in execution_income_terms) or (
            "收入" in question and "支付" not in question
        ):
            add("execution_income")
        if "核销GMV" in question:
            add("execution_gmv")
        if "人次" in question:
            add("execution_visit_count")
        if any(term in question for term in ("核销人数", "核销人头", "涉及多少客人")):
            add("execution_user_count")
        if "客单价" in question and "支付" not in question:
            add("execution_aov_by_visit")
        return augmented

    def _question_requests_named_channel_set(self, question: str) -> bool:
        return all(term in question for term in ("私域", "公域", "老带新"))

    def _named_item_filter_value(self, question: str) -> str:
        item_name = extract_item_name(question)
        if item_name:
            return item_name
        for item_name in ("奇迹胶原", "BBL HERO", "奇迹童颜", "热玛吉"):
            if item_name in question:
                return item_name
        return ""

    def _question_requests_store_breakdown(self, question: str) -> bool:
        return any(
            term in question
            for term in ("\u95e8\u5e97", "\u673a\u6784", "\u533b\u9662", "\u5404\u5e97", "\u5e97\u94fa")
        )

    def _question_requests_this_month_mtd(self, question: str) -> bool:
        return any(term in question for term in ("\u672c\u6708", "\u8fd9\u4e2a\u6708", "\u5f53\u6708"))

    def _remove_rolling_30d_time_instructions(self, instructions: list[str]) -> list[str]:
        return [
            instruction
            for instruction in instructions
            if not (
                "\u6700\u8fd130\u5929" in instruction
                or "last_30d" in instruction
                or "DATE_SUB(CURRENT_DATE(), 30)" in instruction
                or "DATE_SUB(CURRENT_DATE(),30)" in instruction
            )
        ]

    def _requested_group_dimensions(self, question: str) -> list[str]:
        dimensions: list[str] = []
        dimension_rules = [
            ("\u54c1\u9879", ("\u5404\u54c1\u9879", "\u6309\u54c1\u9879", "\u54c1\u9879TOP", "\u54c1\u9879\u6392\u884c")),
            ("\u95e8\u5e97", ("\u5404\u95e8\u5e97", "\u6309\u95e8\u5e97", "\u95e8\u5e97TOP", "\u95e8\u5e97\u6392\u884c")),
            ("\u57ce\u5e02", ("\u5404\u57ce\u5e02", "\u6309\u57ce\u5e02", "\u5206\u57ce\u5e02", "\u57ce\u5e02\u5bf9\u6bd4")),
            ("\u6e20\u9053", ("\u5404\u6e20\u9053", "\u6309\u6e20\u9053", "\u5206\u6e20\u9053", "\u6e20\u9053\u5bf9\u6bd4")),
            ("\u65b0\u8001\u5ba2", ("\u65b0\u8001\u5ba2", "\u65b0\u5ba2\u548c\u8001\u5ba2", "\u65b0\u5ba2\u8001\u5ba2")),
        ]
        for dimension, triggers in dimension_rules:
            if any(trigger in question for trigger in triggers):
                dimensions.append(dimension)
        return dimensions

    def _question_has_named_city(self, question: str) -> bool:
        return any(
            term in question
            for term in (
                "\u5317\u4eac", "\u4e0a\u6d77", "\u5e7f\u5dde", "\u6df1\u5733",
                "\u6b66\u6c49", "\u676d\u5dde", "\u6210\u90fd", "\u91cd\u5e86",
                "\u5929\u6d25", "\u5357\u4eac", "\u82cf\u5dde", "\u897f\u5b89",
                "\u90d1\u5dde", "\u957f\u6c99", "\u9752\u5c9b", "\u5b81\u6ce2",
                "\u5408\u80a5", "\u4f5b\u5c71", "\u4e1c\u839e",
            )
        )

    def _looks_like_store_grouping_instruction(self, instruction: str) -> bool:
        return (
            ("\u95e8\u5e97" in instruction or "tenant_id" in instruction or "sy_hospital_name" in instruction)
            and (
                "\u805a\u5408" in instruction
                or "\u5206\u7ec4" in instruction
                or "\u8f93\u51fa" in instruction
                or "\u8fd4\u56de" in instruction
                or "tenant_name" in instruction
                or "GROUP" in instruction.upper()
                or "SUM(" in instruction.upper()
                or "COUNT(" in instruction.upper()
            )
        )

    def _contains_store_output(self, output_target: str) -> bool:
        return (
            "\u95e8\u5e97" in output_target
            or "tenant_id" in output_target
            or "sy_hospital_name" in output_target
        )

    def list_demo_questions(self) -> list[dict]:
        return [
            {
                "case_id": case["case_id"],
                "template_id": case["template_id"],
                "question": case["question"],
                "business_domain": case["business_domain"],
            }
            for case in self.demo_cases
        ]

    def _match_case(
        self,
        question: str,
        retrieval_context: RetrievalContext | None = None,
        semantic_contract: SemanticContract | None = None,
    ) -> dict:
        if semantic_contract and semantic_contract.template_id in self.cases_by_template:
            return self.cases_by_template[semantic_contract.template_id]
        if semantic_contract and semantic_contract.template_id in {
            ITEM_INCOME_PROGRESS_TEMPLATE,
            "miracle_collagen_income_progress_mtd",
        }:
            item_name = extract_item_name(question) or "奇迹胶原"
            return {
                "case_id": "Q_P1_ITEM_PROGRESS",
                "template_id": ITEM_INCOME_PROGRESS_TEMPLATE,
                "question": f"{item_name}本月核销收入时间进度达成率是多少？",
                "business_domain": "连锁经营-目标进度",
                "metrics": [ITEM_INCOME_PROGRESS_METRIC],
                "dimensions": [],
                "source_tables": [
                    "soyoung_dw.dm_opt_qy_user_execution_record_all_d",
                    "soyoung_dw.dim_channel_month_income_target",
                ],
                "risk_flags": [
                    "实际值使用核销收入 exe_income",
                    "目标值使用 dim_channel_month_income_target.target_absolute_value",
                    f"品项过滤使用 standard_name REGEXP '{item_name}' 和 third_level_hierarchy REGEXP '{item_name}'",
                    "时间进度默认截至昨天",
                ],
            }

        if retrieval_context:
            template_id = retrieval_context.top_template_id()
            if template_id in self.cases_by_template:
                return self.cases_by_template[template_id]

        normalized_question = self._normalize(question)

        for demo_case in self.demo_cases:
            if self._normalize(demo_case["question"]) == normalized_question:
                return demo_case

        keyword_routes = [
            ("pay_to_verify_rate_30d", ["支付后", "核销率"]),
            ("upgrade_execution_30d", ["升单"]),
            ("unverified_amount_store_top10", ["待核销"]),
            ("new_customer_payment_30d", ["新客", "支付"]),
            ("zero_income_orders_30d", ["0元"]),
            ("zero_income_orders_30d", ["0 元"]),
            ("standard_item_penetration_90d", ["渗透率"]),
            ("standard_item_income_top20_30d", ["品项", "TOP"]),
            ("revenue_category_execution_30d", ["大单品"]),
            ("revenue_category_execution_30d", ["常规品"]),
            ("revenue_category_execution_30d", ["大师团"]),
            ("new_old_customer_execution_30d", ["新客", "老客", "核销"]),
            ("channel_execution_30d", ["私域", "公域"]),
            ("channel_execution_30d", ["老带新"]),
            ("private_new_customer_income_this_week", ["私域", "新客", "本周"]),
            ("store_income_top10_30d", ["门店", "TOP"]),
            ("store_income_top10_30d", ["门店", "排行"]),
            ("execution_summary_yesterday", ["昨天", "整体"]),
        ]

        for template_id, keywords in keyword_routes:
            if all(keyword in question for keyword in keywords):
                return self.cases_by_template[template_id]

        return self.cases_by_template["store_income_top10_30d"]

    def _merge_contract_values(self, primary: list[str], contract_values: list[str]) -> list[str]:
        merged = list(primary)
        for value in contract_values:
            if value and value not in merged:
                merged.append(value)
        return merged

    def _semantics_time_label(self, time_type: str) -> str:
        """Convert query_semantics time_type to display label."""
        return {
            "yesterday": "昨天",
            "this_week": "本周",
            "this_month_mtd": "本月MTD（自然月1日至昨天）",
            "last_30d": "最近30天",
            "last_90d": "最近90天",
            "last_60d": "最近60天",
            "as_of_yesterday": "截至昨天",
        }.get(time_type, "")

    def _infer_time_range(self, template_id: str) -> str:
        if "yesterday" in template_id:
            return "昨天"
        if "this_week" in template_id:
            return "本周"
        if "90d" in template_id:
            return "最近90天"
        if "60" in template_id or template_id == "pay_to_verify_rate_30d":
            return "最近60天成熟期 cohort"
        if "unverified" in template_id:
            return "截至昨天"
        return "最近30天"

    def _infer_filters(self, template_id: str) -> list[str]:
        common_execution_filters = [
            "dp = DATE_SUB(CURRENT_DATE(),1)",
            "is_valid = 1",
        ]
        filter_map = {
            "execution_summary_yesterday": common_execution_filters + ["executed_date = DATE_SUB(CURRENT_DATE(),1)"],
            "store_income_top10_30d": common_execution_filters + ["executed_date BETWEEN DATE_SUB(CURRENT_DATE(),30) AND DATE_SUB(CURRENT_DATE(),1)"],
            "private_new_customer_income_this_week": common_execution_filters + [
                "executed_date >= DATE_SUB(CURRENT_DATE(), WEEKDAY(CAST(CURRENT_DATE() AS DATETIME)))",
                "executed_date <= DATE_SUB(CURRENT_DATE(),1)",
                "is_new = 1",
                "cx_first_channel = '私域'",
            ],
            "channel_execution_30d": common_execution_filters + ["cx_first_channel IN ('私域','公域','老带新')"],
            "new_old_customer_execution_30d": common_execution_filters,
            "revenue_category_execution_30d": common_execution_filters + ["revenue_category IN ('大单品','常规品','大师团')"],
            "standard_item_income_top20_30d": common_execution_filters,
            "standard_item_penetration_90d": common_execution_filters + ["standard_name REGEXP '奇迹胶原'"],
            ITEM_INCOME_PROGRESS_TEMPLATE: common_execution_filters + [
                "standard_name REGEXP '<item_name>'",
                "executed_date BETWEEN DATE_FORMAT(CAST(CURRENT_DATE() AS TIMESTAMP), 'yyyy-MM-01') AND DATE_SUB(CURRENT_DATE(),1)",
                "target.month = DATE_FORMAT(CAST(CURRENT_DATE() AS TIMESTAMP), 'yyyy-MM')",
                "target.first_level_hierarchy = '货'",
                "target.second_level_hierarchy = '大单品'",
                "target.third_level_hierarchy REGEXP '<item_name>'",
                "target.fourth_level_hierarchy = '整体'",
                "target.target_type = '收入'",
            ],
            "zero_income_orders_30d": common_execution_filters + ["exe_income = 0"],
            "unverified_amount_store_top10": ["a.dp = DATE_SUB(CURRENT_DATE(),1)", "left_num > 0"],
            "new_customer_payment_30d": ["dp = DATE_SUB(CURRENT_DATE(),1)", "is_paydate_cash = 0", "is_pay_new = 1"],
            "pay_to_verify_rate_30d": ["支付表 is_paydate_cash = 0", "核销表 is_valid = 1"],
            "upgrade_execution_30d": common_execution_filters + ["is_up = 1"],
        }
        return filter_map.get(template_id, [])

    def _build_planning_evidence(
        self,
        demo_case: dict,
        retrieval_context: RetrievalContext | None,
    ) -> list[str]:
        evidence = [
            f"模板选择：{demo_case['case_id']} / {demo_case['template_id']}",
        ]
        if not retrieval_context:
            evidence.append("规划依据：未传入 RetrievalContext，使用规则与样例路由")
            return evidence

        evidence.extend(
            f"采纳指标证据：{mid}"
            for mid in retrieval_context.top_metric_ids()
        )
        evidence.extend(
            f"采纳字段证据：{fn}"
            for fn in retrieval_context.top_field_names()
        )
        evidence.extend(
            f"采纳表证据：{tn}"
            for tn in retrieval_context.top_table_names()
        )
        evidence.extend(
            f"采纳样例证据：{eid}"
            for eid in retrieval_context.top_example_ids()
        )
        evidence.extend(
            f"口径风险：{risk}"
            for risk in dict.fromkeys(retrieval_context.risks)
        )
        return evidence

    def _build_schema_evidence(
        self,
        retrieval_context: RetrievalContext | None,
    ) -> list[str]:
        if not retrieval_context:
            return []

        evidence: list[str] = []
        seen: set[str] = set()
        for hit in retrieval_context.fields[:8]:
            full_name = hit.metadata.get("full_name")
            field_name = hit.metadata.get("field_name")
            business_name = hit.metadata.get("business_name")
            key = full_name or field_name
            if not key or key in seen:
                continue
            seen.add(key)
            if full_name:
                evidence.append(f"字段证据：{full_name}（{business_name or field_name}）")
            elif field_name:
                evidence.append(f"字段证据：{field_name}")
        return evidence

    def _build_query_plan_cot(
        self,
        demo_case: dict,
        retrieval_context: RetrievalContext | None,
        schema_graph: SchemaGraph | None,
    ) -> list[QueryPlanCoT]:
        if not schema_graph and not retrieval_context:
            return []

        database = self._infer_cot_database(demo_case)
        processing_objects = self._build_processing_objects(schema_graph, retrieval_context)
        operation_instructions = self._build_operation_instructions(
            demo_case, schema_graph, retrieval_context,
        )
        output_target = self._infer_cot_output_target(demo_case, schema_graph)

        return [
            QueryPlanCoT(
                step=1,
                database=database,
                processing_objects=processing_objects,
                operation_instructions=operation_instructions,
                output_target=output_target,
                evidence=self._cot_evidence(schema_graph, retrieval_context),
            )
        ]

    # ------------------------------------------------------------------
    # CoT four-tuple helpers
    # ------------------------------------------------------------------

    def _infer_cot_database(self, demo_case: dict) -> str:
        """Extract database name from source_tables.

        All current tables use soyoung_dw. When multi-database support
        arrives this will parse each table's database prefix.
        """
        source_tables = demo_case.get("source_tables", [])
        if source_tables:
            first_table = source_tables[0]
            if "." in first_table:
                return first_table.split(".", 1)[0]
        return "soyoung_dw"

    def _build_processing_objects(
        self,
        schema_graph: SchemaGraph | None,
        retrieval_context: RetrievalContext | None,
    ) -> list[str]:
        """Build processing_objects list: table.field entries + join relations.

        Format aligns with AskData reference:
        - "table_name.field_name" for each involved field
        - "source_table.source_field <-> target_table.target_field" for joins
        """
        objects: list[str] = []

        if schema_graph:
            # Add table.field entries
            for field in schema_graph.fields[:20]:
                table_name = field.get("table_name", "")
                field_name = field.get("field_name", "")
                if table_name and field_name:
                    objects.append(f"{table_name}.{field_name}")

            # Add join relations
            for relation in schema_graph.relations[:10]:
                src_table = relation.get("source_table", "")
                src_field = relation.get("source_field", "")
                tgt_table = relation.get("target_table", "")
                tgt_field = relation.get("target_field", "")
                if src_table and src_field and tgt_table and tgt_field:
                    objects.append(
                        f"{src_table}.{src_field} <-> {tgt_table}.{tgt_field}"
                    )

        if not objects and retrieval_context:
            for field_name in retrieval_context.top_field_names(limit=12):
                objects.append(field_name)

        return objects

    def _build_operation_instructions(
        self,
        demo_case: dict,
        schema_graph: SchemaGraph | None,
        retrieval_context: RetrievalContext | None,
    ) -> list[str]:
        """Generate chain-of-thought operation instructions.

        Returns a list of ordered steps describing the execution plan:
        ["先筛选...", "再关联...", "然后聚合/分组...", "最后排序/截断..."]
        """
        template_id = demo_case["template_id"]
        filters = self._infer_filters(template_id)
        instructions: list[str] = []

        # Step 1: filtering (WHERE)
        filter_parts = []
        if filters:
            filter_parts.extend(filters)
        if filter_parts:
            instructions.append(
                "先筛选："
                + "；".join(f"{part}" for part in filter_parts)
            )
        else:
            instructions.append("先筛选：按业务日期范围过滤有效记录")

        # Step 2: joining (JOIN)
        if schema_graph and schema_graph.relations:
            join_desc_parts = []
            for relation in schema_graph.relations[:5]:
                src = f"{relation.get('source_table', '')}.{relation.get('source_field', '')}"
                tgt = f"{relation.get('target_table', '')}.{relation.get('target_field', '')}"
                desc = relation.get("relation_description", "")
                if src and tgt:
                    join_desc_parts.append(
                        f"{src} = {tgt}"
                        + (f"（{desc}）" if desc else "")
                    )
            if join_desc_parts:
                instructions.append("再关联：" + "；".join(join_desc_parts))
        else:
            instructions.append("再关联：单表查询，无需表关联")

        # Step 3: aggregation / grouping
        calc = self._infer_cot_calculation(template_id, [])
        dimensions = [
            d.get("field", "")
            for d in demo_case.get("dimensions", [])
            if d.get("field")
        ]
        if dimensions and calc:
            instructions.append(
                f"然后聚合：按{', '.join(dimensions)}分组，计算{calc}"
            )
        elif dimensions:
            instructions.append(
                f"然后聚合：按{', '.join(dimensions)}分组统计"
            )
        elif calc:
            instructions.append(f"然后聚合：计算{calc}")
        else:
            instructions.append("然后聚合：汇总统计")

        # Step 4: ordering / limiting
        source_tables = demo_case.get("source_tables", [])
        if "top" in template_id.lower() or "排行" in demo_case.get("question", ""):
            instructions.append("最后排序：按结果值降序排列并截取TOP-N")
        elif "ORDER BY" in str(filters):
            instructions.append("最后排序：按指定字段排序并限制返回行数")
        else:
            instructions.append("最后输出：返回查询结果")

        return instructions

    def _infer_cot_output_target(
        self,
        demo_case: dict,
        schema_graph: SchemaGraph | None,
    ) -> str:
        """Determine the output target (corresponds to SQL SELECT clause)."""
        metrics = demo_case.get("metrics", [])
        dimensions = [
            d.get("alias", d.get("field", ""))
            for d in demo_case.get("dimensions", [])
        ]

        parts = []
        # Resolve metric display names
        for metric_id in metrics:
            metric = self.metric_registry.get(metric_id)
            if metric:
                parts.append(metric.display_name)
            else:
                parts.append(metric_id)

        if dimensions:
            parts[:0] = dimensions

        return "、".join(parts) if parts else demo_case.get("question", "")

    # ------------------------------------------------------------------
    # Legacy helpers (kept for _build_operation_instructions compatibility)
    # ------------------------------------------------------------------

    def _infer_cot_calculation(self, template_id: str, fields: list[str]) -> str:
        if template_id == ITEM_INCOME_PROGRESS_TEMPLATE:
            return "(actual_exe_income / target_exe_income) / (elapsed_days / month_days)"
        if template_id == "unverified_amount_store_top10":
            return "SUM(left_gmv)"
        if "payment" in template_id:
            return "SUM(pay_gmv)"
        if "execution" in template_id or "income" in template_id:
            return "SUM(exe_income)"
        return ", ".join(fields[:3]) if fields else "SUM(exe_income)"

    def _cot_evidence(
        self,
        schema_graph: SchemaGraph | None,
        retrieval_context: RetrievalContext | None,
    ) -> list[str]:
        evidence: list[str] = []
        if schema_graph:
            for field in schema_graph.fields[:5]:
                full_name = field.get("full_name") or field.get("field_name")
                if full_name:
                    evidence.append(f"\u5b57\u6bb5\u8bc1\u636e\uff1a{full_name}")
            if schema_graph.schema_graph_text:
                evidence.append("\u5df2\u6784\u5efa Schema Graph")
        elif retrieval_context:
            for field_name in retrieval_context.top_field_names(limit=5):
                evidence.append(f"\u5b57\u6bb5\u8bc1\u636e\uff1a{field_name}")
        return evidence

    def _merge_retrieved_tables(
        self,
        source_tables: list[str],
        retrieval_context: RetrievalContext | None,
    ) -> list[str]:
        if not retrieval_context:
            return source_tables

        merged = source_tables.copy()
        for hit in retrieval_context.tables:
            full_name = hit.metadata.get("full_name")
            if full_name and full_name not in merged:
                merged.append(full_name)
        return merged

    def _normalize(self, text: str) -> str:
        return "".join(text.split()).lower()
