"""Lightweight business semantic contract for Chain-AskData.

The contract is a deterministic guardrail layer, not a new agent.  It
normalizes high-risk business wording into metrics, dimensions, filters,
and template hints that the existing planner and SQL gate can consume.
"""

import re
from dataclasses import dataclass, field
from typing import Any

from app.knowledge_indexer.retrieval_context import RetrievalContext
from app.business.item_progress import (
    ITEM_INCOME_PROGRESS_METRIC,
    ITEM_INCOME_PROGRESS_TEMPLATE,
    is_item_income_progress_question,
)
from app.models.query import SemanticContract


AREA_NAMES = ("华北", "华东", "华南", "华中")


@dataclass
class SemanticState:
    """Normalized business meaning before it becomes SQL constraints.

    The class stays local to the existing contract module so the pipeline gets
    a real semantic layer without growing a new package too early.
    """

    domain: str = ""
    metrics: list[str] = field(default_factory=list)
    dimensions: list[str] = field(default_factory=list)
    filters: list[str] = field(default_factory=list)
    time_range: str = ""
    top_n: int | None = None
    grain: str = ""
    calculation: str = ""


class SemanticContractBuilder:
    """Build a small deterministic contract from the raw question."""

    def build(
        self,
        question: str,
        retrieval_context: RetrievalContext | None = None,
        *,
        delta: Any | None = None,
        previous_state: Any | None = None,
    ) -> SemanticContract:
        q = question.strip()

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

        state = self._parse_state(q, delta=delta, previous_state=previous_state)
        return self._state_to_contract(q, state)

    def _parse_state(
        self,
        question: str,
        *,
        delta: Any | None = None,
        previous_state: Any | None = None,
    ) -> SemanticState:
        metrics = self._metrics(question)
        dimensions = self._dimensions(question)
        top_n = self._top_n(question)
        time_range = self._time_range(question)

        if previous_state and top_n is None:
            top_n = getattr(previous_state, "top_n", None)

        if previous_state and self._is_metric_switch_to_payment(question, delta):
            metrics = self._payment_metrics_from_question(question)
            if not metrics:
                metrics = ["payment_gmv"]
            dimensions = self._dimensions_after_delta(question, previous_state, dimensions, delta)

        if previous_state and self._is_metric_switch_to_execution(question, delta):
            metrics = ["execution_income"]
            dimensions = self._dimensions_after_delta(question, previous_state, dimensions, delta)

        if previous_state and self._removes_store_dimension(question, delta):
            dimensions = [dim for dim in dimensions if dim != "sy_hospital_name"]
            top_n = None

        filters = self._filters(question, metrics)
        state = SemanticState(
            domain=self._domain(metrics, filters),
            metrics=metrics,
            dimensions=dimensions,
            filters=filters,
            time_range=time_range,
            top_n=top_n,
            grain=self._grain(question, dimensions, top_n),
            calculation=self._calculation(question, metrics),
        )
        return state

    def _state_to_contract(self, question: str, state: SemanticState) -> SemanticContract:
        required_fields = self._required_fields_for_state(state)

        return SemanticContract(
            intent="nl2sql",
            domain=state.domain,
            metrics=state.metrics,
            dimensions=state.dimensions,
            filters=state.filters,
            time_range=state.time_range,
            required_fields=required_fields,
            template_id=self._template_hint_from_state(question, state),
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
            if any(
                term in question
                for term in (
                    "支付GMV", "支付 GMV", "支付收入", "支付金额", "支付额",
                    "收款金额", "收款", "流水", "付了多少", "支付", "付款",
                    "付的", "按支付日",
                )
            ):
                add("payment_gmv")
            if any(term in question for term in ("支付人数", "多少人付", "付的", "人付")):
                add("payment_user_count")
            if any(term in question for term in ("客单价", "人均")):
                add("payment_aov_by_user_day")

        if execution_context:
            if any(term in question for term in ("核销收入", "核销了多少钱", "核销金额", "消耗金额", "业绩", "成交后收入", "按核销日")):
                add("execution_income")
            if "收入" in question and not payment_context:
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
        if self._requests_area_breakdown(question):
            add("area_name")
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
        city = self._named_city(question)
        if city:
            add(f"city_name LIKE '%{city}%'")
        area = self._named_area(question)
        if area:
            add(f"area_name LIKE '%{area}%'")
        store = self._named_store(question)
        if store:
            add(f"sy_hospital_name LIKE '%{store}%'")
        item = self._named_item(question)
        if item:
            add(f"standard_name REGEXP '{item}'")
        if "0元单" in question or "0 元单" in question or "0元核销" in question or "0 元核销" in question:
            add("exe_income = 0")
        return filters

    def _required_fields_for_state(self, state: SemanticState) -> list[str]:
        fields: list[str] = []

        def add(field: str) -> None:
            if field and field not in fields:
                fields.append(field)

        for metric in state.metrics:
            for field_name in _FIELDS_BY_METRIC.get(metric, []):
                add(field_name)
        for dimension in state.dimensions:
            add(dimension)
        for filter_text in state.filters:
            for field_name in (
                "left_num", "is_paydate_cash", "revenue_category", "is_pay_new",
                "is_new", "exe_income", "city_name", "area_name", "standard_name",
                "sy_hospital_name", "cx_first_channel", "pay_gmv", "pay_date",
            ):
                if field_name in filter_text:
                    add(field_name)
        return fields

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
            for field in (
                "left_num", "is_paydate_cash", "revenue_category", "is_pay_new",
                "is_new", "exe_income", "city_name", "area_name", "standard_name",
                "sy_hospital_name",
            ):
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

    def _top_n(self, question: str) -> int | None:
        match = re.search(r"(?i)\btop\s*(\d+)", question)
        if match:
            return int(match.group(1))
        match = re.search(r"前\s*(\d+)", question)
        if match:
            return int(match.group(1))
        return None

    def _grain(self, question: str, dimensions: list[str], top_n: int | None) -> str:
        if "整体" in question or not dimensions:
            return "overall"
        if "sy_hospital_name" in dimensions:
            return "by_store_topn" if top_n else "by_store"
        if "area_name" in dimensions:
            return "by_area_topn" if top_n else "by_area"
        if "standard_name" in dimensions:
            return "by_item_topn" if top_n else "by_item"
        if "cx_first_channel" in dimensions:
            return "by_channel"
        if "is_new" in dimensions:
            return "by_customer_type"
        if "revenue_category" in dimensions:
            return "by_revenue_category"
        return "by_dimension"

    def _calculation(self, question: str, metrics: list[str]) -> str:
        if ITEM_INCOME_PROGRESS_METRIC in metrics or "进度达成率" in question:
            return "progress_rate"
        if "支付后" in question and "核销率" in question:
            return "conversion_rate"
        if "渗透率" in question:
            return "penetration"
        if "占比" in question:
            return "ratio"
        if any(term in question for term in ("对比", "分别", "各")):
            return "compare"
        return "aggregate"

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
        if "payment_gmv" in metrics and any(term in question for term in ("门店", "机构", "医院")) and any(term in question for term in ("TOP", "前", "排行")):
            return "payment_gmv_store_topn_30d"
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
        if "收入占比" in question and any(term in question for term in ("品项", "项目")):
            return "standard_item_income_share_top20_30d"
        if any(term in question for term in ("品项", "项目")) and any(term in question for term in ("TOP", "前", "排行", "最高")):
            return "standard_item_income_top20_30d"
        if any(term in question for term in ("门店", "机构", "医院")) and any(term in question for term in ("TOP", "前", "排行")):
            return "store_income_top10_30d"
        if "新客" in question and "老客" in question:
            return "new_old_customer_execution_30d"
        if any(term in question for term in ("私域", "公域", "老带新")):
            return "channel_execution_30d"
        if "整体" in question and "execution_income" in metrics:
            return "execution_income_summary_30d"
        return ""

    def _template_hint_from_state(self, question: str, state: SemanticState) -> str:
        metrics = state.metrics
        if ITEM_INCOME_PROGRESS_METRIC in metrics:
            return ITEM_INCOME_PROGRESS_TEMPLATE
        if state.calculation == "conversion_rate":
            return "pay_to_verify_rate_30d"
        if "unverified_amount" in metrics:
            return "unverified_amount_store_top10"
        if "payment_gmv" in metrics and "execution_income" in metrics:
            return "pay_to_verify_rate_30d"
        if state.domain == "payment":
            if "area_name" in state.dimensions:
                return "area_payment_30d"
            if "sy_hospital_name" in state.dimensions and state.top_n:
                return "payment_gmv_store_topn_30d"
            if "is_pay_new = 1" in state.filters or "新客" in question:
                return "new_customer_payment_30d"
            return "payment_gmv_summary_30d"
        if "standard_item_penetration" in metrics:
            return "standard_item_penetration_90d"
        if "zero_income_order_count" in metrics:
            return "zero_income_orders_30d"
        if "升单" in question:
            return "upgrade_execution_30d"
        if "revenue_category" in state.dimensions:
            return "revenue_category_execution_30d"
        if "area_name" in state.dimensions:
            return "area_execution_30d"
        if state.calculation == "ratio" and "standard_name" in state.dimensions:
            return "standard_item_income_share_top20_30d"
        if "standard_name" in state.dimensions and state.top_n:
            return "standard_item_income_top20_30d"
        if "sy_hospital_name" in state.dimensions and state.top_n:
            return "store_income_top10_30d"
        if "area_name" in state.dimensions:
            return "area_execution_30d"
        if "is_new" in state.dimensions:
            return "new_old_customer_execution_30d"
        if "cx_first_channel" in state.dimensions:
            return "channel_execution_30d"
        if state.grain == "overall" and "execution_income" in metrics:
            return "execution_income_summary_30d"
        return self._template_hint(question, metrics)

    def _is_metric_switch_to_payment(self, question: str, delta: Any | None = None) -> bool:
        if "支付后" in question and "核销率" in question:
            return False
        if delta and "domain_switch_to_payment" in getattr(delta, "operations", []):
            return True
        if not self._has_payment_alias(question):
            return False
        return any(term in question for term in ("换成", "改成", "改看", "那", "呢", "本周", "本月", "昨天"))

    def _is_metric_switch_to_execution(self, question: str, delta: Any | None = None) -> bool:
        if delta and "domain_switch_to_execution" in getattr(delta, "operations", []):
            return True
        if not any(term in question for term in ("核销收入", "核销金额", "核销GMV")):
            return False
        return any(term in question for term in ("换成", "改成", "改看", "那", "呢"))

    def _payment_metrics_from_question(self, question: str) -> list[str]:
        metrics: list[str] = ["payment_gmv"]
        if any(term in question for term in ("支付人数", "多少人付", "人付")):
            metrics.append("payment_user_count")
        if any(term in question for term in ("客单价", "人均")):
            metrics.append("payment_aov_by_user_day")
        return metrics

    def _dimensions_after_delta(
        self,
        question: str,
        previous_state: Any,
        dimensions: list[str],
        delta: Any | None,
    ) -> list[str]:
        if self._removes_store_dimension(question, delta):
            return [dim for dim in dimensions if dim != "sy_hospital_name"]
        if dimensions:
            return dimensions
        previous_dimensions = list(getattr(previous_state, "dimensions", []) or [])
        return previous_dimensions

    def _removes_store_dimension(self, question: str, delta: Any | None = None) -> bool:
        if delta and "sy_hospital_name" in getattr(delta, "remove_dimensions", []):
            return True
        return "整体" in question and any(
            term in question
            for term in ("不要门店", "不用门店", "不看门店", "去掉门店", "不按门店")
        )

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
        return self._has_payment_alias(question) or any(term in question for term in ("付了", "付的", "人均", "按支付日"))

    def _has_payment_alias(self, question: str) -> bool:
        return any(
            term in question
            for term in (
                "支付", "付款", "收款", "流水", "支付GMV", "支付 GMV",
                "支付收入", "支付金额", "支付额", "收款金额",
            )
        )

    def _execution_context(self, question: str) -> bool:
        if any(term in question for term in ("待核销", "没核销", "未核销")):
            return False
        return any(
            term in question
            for term in ("核销", "消耗", "业绩", "成交后", "按核销日", "收入", "0元单", "升单")
        )

    def _named_city(self, question: str) -> str:
        for city in (
            "北京", "上海", "广州", "深圳", "武汉", "杭州", "成都", "重庆",
            "天津", "南京", "苏州", "西安", "郑州", "长沙", "青岛", "宁波",
            "合肥", "佛山", "东莞",
        ):
            if city in question:
                return city
        return ""

    def _named_area(self, question: str) -> str:
        for area in AREA_NAMES:
            if area in question:
                return area
        return ""

    def _requests_area_breakdown(self, question: str) -> bool:
        if self._named_area(question):
            return False
        return any(
            term in question
            for term in (
                "各大区", "各地区", "各区域", "各战区",
                "按大区", "按地区", "按区域", "按战区",
                "分大区", "分地区", "分区域", "分战区",
                "大区对比", "地区对比", "区域对比", "战区对比",
            )
        )

    def _named_item(self, question: str) -> str:
        upper_question = question.upper()
        for item in ("奇迹胶原", "奇迹童颜", "BBL HERO", "新一代热玛吉", "热玛吉"):
            if item.upper() in upper_question:
                return item
        return ""

    def _named_store(self, question: str) -> str:
        if any(term in question for term in ("各门店", "各店", "门店TOP", "门店排行")):
            return ""
        if "保利" in question:
            return "保利"
        cleaned = question
        for city in (
            "北京", "上海", "广州", "深圳", "武汉", "杭州", "成都", "重庆",
            "天津", "南京", "苏州", "西安", "郑州", "长沙", "青岛", "宁波",
            "合肥", "佛山", "东莞",
        ):
            cleaned = cleaned.replace(city, "")
        cleaned = re.sub(r"(想看|看一下|看下|只看|单看|那|那个|如果是|换成|改成|呢|的)", "", cleaned)
        match = re.search(r"([\u4e00-\u9fa5A-Za-z0-9 ]{2,20})店", cleaned)
        if not match:
            return ""
        store = match.group(1).strip()
        return store if store and store not in {"门", "门店"} else ""


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
