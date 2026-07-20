"""Lightweight business semantic contract for Chain-AskData.

The contract is a deterministic guardrail layer, not a new agent.  It
normalizes high-risk business wording into metrics, dimensions, filters,
and template hints that the existing planner and SQL gate can consume.
"""

from app.knowledge_indexer.retrieval_context import RetrievalContext
from app.business.item_progress import (
    ITEM_INCOME_PROGRESS_METRIC,
    ITEM_INCOME_PROGRESS_TEMPLATE,
    is_item_income_progress_question,
)
from app.models.query import SemanticContract


class SemanticContractBuilder:
    """Build a small deterministic contract from the raw question."""

    def build(
        self,
        question: str,
        retrieval_context: RetrievalContext | None = None,
    ) -> SemanticContract:
        q = question.strip()
        metrics: list[str] = []
        dimensions: list[str] = []
        filters: list[str] = []
        required_fields: list[str] = []

        if self._is_schema_explain(q):
            return SemanticContract(
                intent="schema_explain",
                domain="schema",
                dimensions=self._dimensions(q),
                required_fields=self._required_fields_for_schema_question(q),
                template_id=self._template_hint(q, []),
            )

        if self._is_caliber_explain(q):
            return SemanticContract(
                intent="caliber_explain",
                domain="caliber",
                metrics=self._metrics(q),
                required_fields=self._required_fields(q),
                template_id=self._template_hint(q, self._metrics(q)),
            )

        if self._is_reject_boundary(q):
            return SemanticContract(
                intent="unknown",
                domain="reject_boundary",
                reject_reason="预测、原因诊断或问题归因类问题不应在当前版本强行生成 SQL",
            )

        metrics = self._metrics(q)
        dimensions = self._dimensions(q)
        filters = self._filters(q, metrics)
        required_fields = self._required_fields(q)

        return SemanticContract(
            intent="nl2sql",
            domain=self._domain(metrics, filters),
            metrics=metrics,
            dimensions=dimensions,
            filters=filters,
            time_range=self._time_range(q),
            required_fields=required_fields,
            template_id=self._template_hint(q, metrics),
        )

    def _is_reject_boundary(self, question: str) -> bool:
        reject_terms = (
            "预测",
            "预估",
            "下个月",
            "为什么",
            "原因",
            "下降",
            "上涨",
            "有问题",
            "诊断",
        )
        diagnostic_phrase = "分析哪个" in question or "帮我分析" in question
        return any(term in question for term in reject_terms) or diagnostic_phrase

    def _is_schema_explain(self, question: str) -> bool:
        if any(term in question for term in ("会员", "membership_level", "L3", "l3")) and any(
            term in question for term in ("怎么知道", "是不是", "哪里取", "字段")
        ):
            return True
        return any(
            term in question
            for term in ("哪个字段", "哪些字段", "用什么字段", "用哪个字段", "应该用哪个字段")
        )

    def _is_caliber_explain(self, question: str) -> bool:
        if "standard_name" in question and "product_name" in question:
            return True
        if any(term in question for term in ("口径", "区别", "差别", "分母", "分子", "定义")):
            return True
        explain_style = any(term in question for term in ("怎么看", "怎么算", "怎么计算", "如何看", "如何算", "如何计算", "应该优先使用"))
        metric_style = any(term in question for term in ("渗透率", "客单价", "占比", "核销", "支付", "GMV", "品项"))
        return explain_style and metric_style

    def _metrics(self, question: str) -> list[str]:
        metrics: list[str] = []

        def add(metric: str) -> None:
            if metric not in metrics:
                metrics.append(metric)

        payment_context = self._payment_context(question)
        execution_context = self._execution_context(question)

        if is_item_income_progress_question(question):
            add(ITEM_INCOME_PROGRESS_METRIC)

        if "待核销" in question or "没核销" in question or "未核销" in question:
            add("unverified_amount")

        if "0元单" in question or "0 元单" in question or "0元核销" in question or "0 元核销" in question:
            add("zero_income_order_count")
            if "客" in question or "人数" in question:
                add("execution_user_count")

        if "渗透率" in question:
            add("standard_item_penetration")

        if "升单" in question:
            add("execution_user_count")
            add("execution_visit_count")
            add("execution_income")

        if payment_context:
            if any(term in question for term in ("支付GMV", "付了多少", "支付", "付的", "按支付日")):
                add("payment_gmv")
            if any(term in question for term in ("支付人数", "多少人付", "付的", "人付")):
                add("payment_user_count")
            if any(term in question for term in ("客单价", "人均")):
                add("payment_aov_by_user_day")

        if execution_context:
            if any(term in question for term in ("核销收入", "核销了多少钱", "核销金额", "消耗金额", "业绩", "成交后收入", "按核销日", "收入")):
                add("execution_income")
            if "核销GMV" in question:
                add("execution_gmv")
            if "人次" in question or "人次占比" in question:
                add("execution_visit_count")
            if any(term in question for term in ("核销人数", "核销人头", "涉及多少客人", "多少客人")):
                add("execution_user_count")
            if "客单价" in question and not payment_context:
                add("execution_aov_by_visit")

        return metrics

    def _dimensions(self, question: str) -> list[str]:
        dimensions: list[str] = []

        def add(dimension: str) -> None:
            if dimension not in dimensions:
                dimensions.append(dimension)

        if any(term in question for term in ("门店", "机构", "医院", "各店", "店铺")):
            add("sy_hospital_name")
        if "城市" in question:
            add("city_name")
        if any(term in question for term in ("渠道", "私域", "公域", "老带新")):
            add("cx_first_channel")
        if any(term in question for term in ("新老客", "新客和老客", "新客老客")):
            add("is_new")
        if any(term in question for term in ("品项", "项目")):
            add("standard_name")
        if any(term in question for term in ("大单品", "常规品", "大师团", "品类", "各品类")):
            add("revenue_category")
        return dimensions

    def _filters(self, question: str, metrics: list[str]) -> list[str]:
        filters: list[str] = []

        def add(filter_text: str) -> None:
            if filter_text not in filters:
                filters.append(filter_text)

        if any(metric.startswith("execution_") or metric in {"zero_income_order_count", "standard_item_penetration"} for metric in metrics):
            add("is_valid = 1")
        if any(metric.startswith("payment_") for metric in metrics):
            add("is_paydate_cash = 0")
        if "新客" in question:
            add("is_pay_new = 1" if any(metric.startswith("payment_") for metric in metrics) else "is_new = 1")
        if "待核销" in question or "没核销" in question or "未核销" in question:
            add("left_num > 0")
        if all(term in question for term in ("大单品", "常规品", "大师团")):
            add("revenue_category IN ('大单品','常规品','大师团')")
        elif "大单品" in question:
            add("revenue_category = '大单品'")
        elif "大师团" in question:
            add("revenue_category = '大师团'")
        elif "常规品" in question:
            add("revenue_category = '常规品'")
        if "私域" in question and not all(term in question for term in ("私域", "公域", "老带新")):
            add("cx_first_channel = '私域'")
        if "公域" in question and not all(term in question for term in ("私域", "公域", "老带新")):
            add("cx_first_channel = '公域'")
        if "老带新" in question and not all(term in question for term in ("私域", "公域", "老带新")):
            add("cx_first_channel = '老带新'")
        if "0元单" in question or "0 元单" in question or "0元核销" in question or "0 元核销" in question:
            add("exe_income = 0")
        return filters

    def _required_fields(self, question: str) -> list[str]:
        fields: list[str] = []

        def add(field: str) -> None:
            if field not in fields:
                fields.append(field)

        for metric in self._metrics(question):
            for field in _FIELDS_BY_METRIC.get(metric, []):
                add(field)
        for dimension in self._dimensions(question):
            add(dimension)
        for filter_text in self._filters(question, self._metrics(question)):
            for field in ("left_num", "is_paydate_cash", "revenue_category", "is_pay_new", "is_new", "exe_income"):
                if field in filter_text:
                    add(field)
        return fields

    def _required_fields_for_schema_question(self, question: str) -> list[str]:
        if any(term in question for term in ("会员", "membership_level", "L3", "l3")):
            return ["membership_level", "crm_customer_id", "user_id"]
        if "门店" in question or "机构" in question:
            return ["sy_hospital_name"]
        if "核销人数" in question:
            return ["customer_id"]
        return []

    def _time_range(self, question: str) -> str:
        if "截至昨天" in question:
            return "as_of_yesterday"
        if "本月" in question or "这个月" in question or "当月" in question:
            return "this_month_mtd"
        if "本周" in question or "这周" in question:
            return "this_week"
        if "昨天" in question:
            return "yesterday"
        if "7" in question:
            return "last_7d"
        if "90" in question:
            return "last_90d"
        if "60" in question:
            return "last_60d"
        return "last_30d"

    def _template_hint(self, question: str, metrics: list[str]) -> str:
        if ITEM_INCOME_PROGRESS_METRIC in metrics:
            return ITEM_INCOME_PROGRESS_TEMPLATE
        if "支付后" in question and "核销率" in question:
            return "pay_to_verify_rate_30d"
        if any(term in question for term in ("本周", "这周")) and "私域" in question and "新客" in question:
            return "private_new_customer_income_this_week"
        if "unverified_amount" in metrics:
            return "unverified_amount_store_top10"
        if "payment_gmv" in metrics and "execution_income" in metrics:
            return "pay_to_verify_rate_30d"
        if any(metric.startswith("payment_") for metric in metrics):
            return "new_customer_payment_30d"
        if "standard_item_penetration" in metrics:
            return "standard_item_penetration_90d"
        if "zero_income_order_count" in metrics:
            return "zero_income_orders_30d"
        if "升单" in question:
            return "upgrade_execution_30d"
        if any(term in question for term in ("大单品", "常规品", "大师团", "品类", "各品类")):
            return "revenue_category_execution_30d"
        if any(term in question for term in ("品项", "项目")) and any(term in question for term in ("TOP", "前", "排行", "最高")):
            return "standard_item_income_top20_30d"
        if any(term in question for term in ("门店", "机构", "医院")) and any(term in question for term in ("TOP", "前", "排行")):
            return "store_income_top10_30d"
        if any(term in question for term in ("私域", "公域", "老带新")):
            return "channel_execution_30d"
        if "新客" in question and "老客" in question:
            return "new_old_customer_execution_30d"
        return ""

    def _domain(self, metrics: list[str], filters: list[str]) -> str:
        has_payment = any(metric.startswith("payment_") for metric in metrics)
        has_execution = any(metric.startswith("execution_") for metric in metrics)
        if "unverified_amount" in metrics:
            return "unverified_inventory"
        if has_payment and has_execution:
            return "payment_execution_mixed"
        if has_payment:
            return "payment"
        if has_execution:
            return "execution"
        return "chain_business"

    def _payment_context(self, question: str) -> bool:
        return any(term in question for term in ("支付", "付了", "付的", "人均", "按支付日", "支付GMV"))

    def _execution_context(self, question: str) -> bool:
        if any(term in question for term in ("待核销", "没核销", "未核销")):
            return False
        return any(
            term in question
            for term in ("核销", "消耗", "业绩", "成交后", "按核销日", "收入", "0元单", "升单")
        )


_FIELDS_BY_METRIC = {
    "item_execution_income_time_progress_rate": [
        "exe_income", "executed_date", "standard_name", "dp", "is_valid",
        "target_absolute_value", "month", "first_level_hierarchy",
        "second_level_hierarchy", "third_level_hierarchy",
        "fourth_level_hierarchy", "target_type",
    ],
    "miracle_collagen_execution_income_time_progress_rate": [
        "exe_income", "executed_date", "standard_name", "dp", "is_valid",
        "target_absolute_value", "month", "first_level_hierarchy",
        "second_level_hierarchy", "third_level_hierarchy",
        "fourth_level_hierarchy", "target_type",
    ],
    "execution_income": ["exe_income", "executed_date", "dp", "is_valid"],
    "execution_gmv": ["exe_amount", "executed_date", "dp", "is_valid"],
    "execution_visit_count": ["verify_date_id", "executed_date", "dp", "is_valid"],
    "execution_user_count": ["customer_id", "executed_date", "dp", "is_valid"],
    "execution_aov_by_visit": ["exe_income", "verify_date_id", "executed_date", "dp", "is_valid"],
    "payment_gmv": ["pay_gmv", "pay_date", "dp", "is_paydate_cash"],
    "payment_user_count": ["uid", "pay_date", "dp", "is_paydate_cash"],
    "payment_aov_by_user_day": ["pay_gmv", "uid", "pay_date", "dp", "is_paydate_cash"],
    "zero_income_order_count": ["main_order_id", "exe_income", "customer_id", "executed_date", "dp", "is_valid"],
    "standard_item_penetration": ["standard_name", "customer_id", "executed_date", "dp", "is_valid"],
    "unverified_amount": ["left_gmv", "left_num", "dp"],
}
