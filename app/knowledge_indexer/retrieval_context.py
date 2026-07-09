from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class RetrievalHit:
    """结构化检索命中项。"""

    document: str
    metadata: dict[str, Any]
    distance: float
    rerank_score: float


@dataclass
class RetrievalContext:
    """供 QueryPlanner 消费的结构化 RAG 上下文。"""

    query: str
    metrics: list[RetrievalHit] = field(default_factory=list)
    fields: list[RetrievalHit] = field(default_factory=list)
    tables: list[RetrievalHit] = field(default_factory=list)
    relations: list[RetrievalHit] = field(default_factory=list)
    examples: list[RetrievalHit] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    raw_matches: list[dict[str, Any]] = field(default_factory=list)

    def has_meaningful_evidence(self) -> bool:
        """True when retrieval returned structurally useful evidence.

        Vector search on ChromaDB always returns nearest neighbours even for
        completely unrelated queries.  A response with only metrics and no
        fields/tables/examples is almost certainly out-of-domain noise.
        """
        return bool(
            self.fields
            or self.tables
            or self.examples
            or (self.metrics and (self.fields or self.tables))
        )

    def top_metric_ids(self, limit: int = 3) -> list[str]:
        return list(dict.fromkeys(
            hit.metadata.get("canonical") or hit.metadata["metric_id"]
            for hit in self.metrics
            if hit.metadata.get("canonical") or hit.metadata.get("metric_id")
        ))[:limit]

    def top_table_names(self, limit: int = 3) -> list[str]:
        return list(dict.fromkeys(
            hit.metadata["table_name"]
            for hit in self.tables
            if hit.metadata.get("table_name")
        ))[:limit]

    def top_field_names(self, limit: int = 8) -> list[str]:
        return list(dict.fromkeys(
            hit.metadata["field_name"]
            for hit in self.fields
            if hit.metadata.get("field_name")
        ))[:limit]

    def top_example_ids(self, limit: int = 3) -> list[str]:
        return list(dict.fromkeys(
            hit.metadata["case_id"]
            for hit in self.examples
            if hit.metadata.get("case_id")
        ))[:limit]

    def top_template_id(self) -> str | None:
        for hit in self.examples:
            template_id = hit.metadata.get("template_id")
            if template_id:
                return template_id
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "metrics": [hit.__dict__ for hit in self.metrics],
            "fields": [hit.__dict__ for hit in self.fields],
            "tables": [hit.__dict__ for hit in self.tables],
            "relations": [hit.__dict__ for hit in self.relations],
            "examples": [hit.__dict__ for hit in self.examples],
            "risks": self.risks,
        }


class RetrievalContextBuilder:
    """把 Chroma 原始命中列表转换成结构化 RetrievalContext。"""

    def build(self, query: str, matches: list[dict[str, Any]]) -> RetrievalContext:
        context = RetrievalContext(query=query, raw_matches=matches)

        for match in matches:
            hit = self._to_hit(match)
            asset_type = hit.metadata.get("asset_type")
            if asset_type == "metric":
                context.metrics.append(hit)
            elif asset_type == "field":
                context.fields.append(hit)
            elif asset_type == "table":
                context.tables.append(hit)
            elif asset_type == "relation":
                context.relations.append(hit)
            elif asset_type == "demo_query":
                context.examples.append(hit)

        context.metrics.sort(key=lambda hit: -hit.rerank_score)
        context.fields.sort(key=lambda hit: -hit.rerank_score)
        context.tables.sort(key=lambda hit: -hit.rerank_score)
        context.relations.sort(key=lambda hit: -hit.rerank_score)
        context.examples.sort(key=lambda hit: -hit.rerank_score)
        context.risks.extend(self._infer_risks(query, context))
        return context

    def _to_hit(self, match: dict[str, Any]) -> RetrievalHit:
        return RetrievalHit(
            document=match.get("document", ""),
            metadata=match.get("metadata", {}) or {},
            distance=float(match.get("distance", 0.0)),
            rerank_score=float(match.get("rerank_score", 0.0)),
        )

    def _infer_risks(self, query: str, context: RetrievalContext) -> list[str]:
        risks: list[str] = []
        if "客单价" in query and "核销" not in query and "支付" not in query:
            risks.append("客单价存在核销口径与支付口径，请确认业务场景")
        if "收入" in query and any("GMV" in hit.document for hit in context.metrics):
            risks.append("收入与 GMV 口径不同，核销收入应使用 exe_income")
        return risks
