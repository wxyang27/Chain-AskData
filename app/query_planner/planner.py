from app.assets.loader import load_yaml_asset
from app.knowledge_indexer.retrieval_context import RetrievalContext
from app.metric_registry.registry import MetricRegistry
from app.models.query import DimensionPlan, QueryPlan, QueryPlanCoT
from app.schema_retrieval.retriever import SchemaRetriever
from app.schema_graph.graph import SchemaGraph


class QueryPlanner:
    """自然语言到 QueryPlan 的确定性规划器。

    MVP 阶段仍采用 template-first 路线，但会消费 RetrievalContext，把 RAG 命中的
    指标、字段、表、样例和风险写回 QueryPlan，便于解释和后续 SQL 生成。
    """

    def __init__(self):
        self.metric_registry = MetricRegistry()
        self.schema_retriever = SchemaRetriever()
        self.demo_cases = load_yaml_asset("knowledge/examples/demo_queries.json")
        self.cases_by_template = {
            case["template_id"]: case
            for case in self.demo_cases
        }

    def plan(
        self,
        question: str,
        retrieval_context: RetrievalContext | None = None,
        schema_graph: SchemaGraph | None = None,
    ) -> QueryPlan:
        demo_case = self._match_case(question, retrieval_context)
        dimensions = [
            DimensionPlan(**dimension)
            for dimension in demo_case.get("dimensions", [])
        ]
        retrieved_metric_ids = retrieval_context.top_metric_ids() if retrieval_context else []
        retrieved_field_names = retrieval_context.top_field_names() if retrieval_context else []
        retrieved_table_names = retrieval_context.top_table_names() if retrieval_context else []
        retrieved_example_ids = retrieval_context.top_example_ids() if retrieval_context else []
        planning_evidence = self._build_planning_evidence(demo_case, retrieval_context)
        schema_evidence = self._build_schema_evidence(retrieval_context)
        query_plan_cot = self._build_query_plan_cot(
            demo_case=demo_case,
            retrieval_context=retrieval_context,
            schema_graph=schema_graph,
        )
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
            sql_strategy="rag_enhanced_template",
            time_range=self._infer_time_range(demo_case["template_id"]),
            metrics=self.metric_registry.get_many(demo_case["metrics"]),
            dimensions=dimensions,
            filters=self._infer_filters(demo_case["template_id"]),
            source_tables=source_tables,
            risk_flags=risk_flags,
            retrieved_metric_ids=retrieved_metric_ids,
            retrieved_field_names=retrieved_field_names,
            retrieved_table_names=retrieved_table_names,
            retrieved_example_ids=retrieved_example_ids,
            planning_evidence=planning_evidence,
            schema_evidence=schema_evidence,
            query_plan_cot=query_plan_cot,
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

    def _match_case(self, question: str, retrieval_context: RetrievalContext | None = None) -> dict:
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
            "private_new_customer_income_this_week": common_execution_filters + ["is_new = 1", "cx_first_channel = '私域'"],
            "channel_execution_30d": common_execution_filters + ["cx_first_channel IN ('私域','公域','老带新')"],
            "new_old_customer_execution_30d": common_execution_filters,
            "revenue_category_execution_30d": common_execution_filters + ["revenue_category IN ('大单品','常规品','大师团')"],
            "standard_item_income_top20_30d": common_execution_filters,
            "standard_item_penetration_90d": common_execution_filters + ["standard_name REGEXP '奇迹胶原'"],
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

        for metric_id in retrieval_context.top_metric_ids():
            evidence.append(f"采纳指标证据：{metric_id}")
        for field_name in retrieval_context.top_field_names():
            evidence.append(f"采纳字段证据：{field_name}")
        for table_name in retrieval_context.top_table_names():
            evidence.append(f"采纳表证据：{table_name}")
        for example_id in retrieval_context.top_example_ids():
            evidence.append(f"采纳样例证据：{example_id}")
        for risk in retrieval_context.risks:
            evidence.append(f"口径风险：{risk}")
        return evidence

    def _build_schema_evidence(
        self,
        retrieval_context: RetrievalContext | None,
    ) -> list[str]:
        if not retrieval_context:
            return []

        evidence: list[str] = []
        for hit in retrieval_context.fields[:8]:
            full_name = hit.metadata.get("full_name")
            field_name = hit.metadata.get("field_name")
            business_name = hit.metadata.get("business_name")
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
