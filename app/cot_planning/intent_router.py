from dataclasses import dataclass, field

from app.knowledge_indexer.retrieval_context import RetrievalContext


@dataclass(frozen=True)
class IntentRouteResult:
    intent: str
    confidence: float
    reason: str
    evidence: list[str] = field(default_factory=list)


class IntentRouter:
    """Deterministic AskData-lite intent router."""

    def route(self, question: str, retrieval_context: RetrievalContext) -> IntentRouteResult:
        normalized = question.lower()
        field_names = retrieval_context.top_field_names(limit=8)
        metric_ids = retrieval_context.top_metric_ids(limit=5)
        example_ids = retrieval_context.top_example_ids(limit=3)

        if self._is_caliber_explain(normalized):
            return IntentRouteResult(
                intent="caliber_explain",
                confidence=0.9,
                reason="\u7528\u6237\u5728\u8be2\u95ee\u6307\u6807\u53e3\u5f84\u3001\u5dee\u5f02\u6216\u5b9a\u4e49",
                evidence=field_names + metric_ids,
            )

        if self._is_schema_explain(normalized):
            return IntentRouteResult(
                intent="schema_explain",
                confidence=0.9,
                reason="\u7528\u6237\u5728\u8be2\u95ee\u5b57\u6bb5\u3001\u8868\u6216 Schema \u6620\u5c04",
                evidence=field_names,
            )

        if self._is_unknown(normalized, retrieval_context):
            return IntentRouteResult(
                intent="unknown",
                confidence=0.7,
                reason="\u5f53\u524d\u77e5\u8bc6\u5e93\u7f3a\u5c11\u53ef\u652f\u6491\u8be5\u95ee\u9898\u7684\u8868\u3001\u5b57\u6bb5\u6216\u6307\u6807\u8bc1\u636e",
                evidence=[],
            )

        return IntentRouteResult(
            intent="nl2sql",
            confidence=0.8 if (metric_ids or example_ids) else 0.6,
            reason="\u95ee\u9898\u5177\u6709\u53d6\u6570\u7279\u5f81\uff0c\u4e14\u6709\u6307\u6807\u6216\u6837\u4f8b\u8bc1\u636e",
            evidence=metric_ids + example_ids,
        )

    def _is_schema_explain(self, normalized_question: str) -> bool:
        if any(term in normalized_question for term in ["会员", "membership_level", "l3"]) and any(
            term in normalized_question for term in ["怎么知道", "是不是", "哪里取", "字段"]
        ):
            return True
        if any(word in normalized_question for word in ["用哪个字段", "哪个字段", "哪些字段"]):
            return True
        schema_words = [
            "\u54ea\u4e2a\u5b57\u6bb5",
            "\u54ea\u4e9b\u5b57\u6bb5",
            "\u7528\u4ec0\u4e48\u5b57\u6bb5",
            "\u5b57\u6bb5",
            "schema",
            "\u8868",
        ]
        explain_words = [
            "\u662f\u4ec0\u4e48",
            "\u5e94\u8be5\u7528",
            "\u600e\u4e48\u5339\u914d",
            "\u89e3\u91ca",
        ]
        return any(word in normalized_question for word in schema_words) and any(
            word in normalized_question for word in explain_words
        )

    def _is_caliber_explain(self, normalized_question: str) -> bool:
        if "standard_name" in normalized_question and "product_name" in normalized_question:
            return True
        caliber_words = [
            "\u53e3\u5f84",
            "\u533a\u522b",
            "\u5dee\u522b",
            "\u6709\u4ec0\u4e48\u4e0d\u540c",
            "\u4ec0\u4e48\u533a\u522b",
            "\u5b9a\u4e49",
            "\u5206\u6bcd",
            "\u5206\u5b50",
            "怎么算",
            "怎么计算",
            "怎么看",
            "如何算",
            "如何计算",
            "如何看",
            "应该优先使用",
        ]
        metric_words = [
            "\u6838\u9500",
            "\u652f\u4ed8",
            "gmv",
            "\u6536\u5165",
            "\u5ba2\u5355\u4ef7",
            "\u4eba\u6570",
            "\u4eba\u6b21",
            "渗透率",
            "占比",
            "0元",
            "品项",
        ]
        return any(word in normalized_question for word in caliber_words) and any(
            word in normalized_question for word in metric_words
        )

    def _is_unknown(self, normalized_question: str, retrieval_context: RetrievalContext) -> bool:
        reject_words = [
            "预测", "预估", "为什么", "原因", "下降", "上涨", "有问题", "诊断",
        ]
        if any(word in normalized_question for word in reject_words):
            return True
        if "帮我分析" in normalized_question or "分析哪个" in normalized_question:
            return True

        unsupported_words = [
            "\u5929\u6c14", "\u6ee1\u610f\u5ea6", "\u80a1\u4ef7", "\u6296\u97f3\u70ed\u699c",
            "\u80a1\u7968", "\u7535\u5f71", "\u5916\u5356", "\u5feb\u9012", "\u673a\u7968", "\u9152\u5e97",
        ]
        if any(word in normalized_question for word in unsupported_words):
            return True
        supported_business_words = [
            "核销", "支付", "待核销", "收入", "gmv", "客单价",
            "门店", "品项", "新客", "老客", "渠道", "升单", "渗透率",
        ]
        if any(word in normalized_question for word in supported_business_words):
            return False
        return not retrieval_context.has_meaningful_evidence()
