import re
from typing import Any


METRIC_PREFIX = "\u6307\u6807\uff1a"
FIELD_WORD = "\u5b57\u6bb5"
AOV_WORD = "\u5ba2\u5355\u4ef7"
DENOMINATOR_WORD = "\u5206\u6bcd"
VISIT_WORD = "\u4eba\u6b21"


class LightweightReranker:
    """Lightweight lexical reranker for the local hash-embedding MVP."""

    def rerank(self, query_text: str, matches: list[dict[str, Any]], top_k: int) -> list[dict[str, Any]]:
        reranked = []
        for match in matches:
            score = self._score(query_text, match)
            item = match.copy()
            item["rerank_score"] = score
            reranked.append(item)

        reranked.sort(key=lambda item: (-item["rerank_score"], item["distance"]))
        return reranked[:top_k]

    def _score(self, query_text: str, match: dict[str, Any]) -> float:
        document = match.get("document", "")
        metadata = match.get("metadata", {}) or {}
        searchable_text = document + "\n" + " ".join(str(value) for value in metadata.values())
        terms = self._terms(query_text)

        score = 0.0
        for term in terms:
            if term and term in searchable_text:
                score += 1.0

        display_name = str(metadata.get("display_name", ""))
        if display_name and display_name in query_text:
            score += 12.0

        asset_type = metadata.get("asset_type")
        if asset_type == "metric" and METRIC_PREFIX in document:
            score += 2.0
        if asset_type == "field":
            score += self._field_score(query_text, metadata)

        if AOV_WORD in query_text and AOV_WORD in searchable_text:
            score += 3.0
        if DENOMINATOR_WORD in query_text and (DENOMINATOR_WORD in searchable_text or VISIT_WORD in searchable_text):
            score += 2.0

        return score

    def _field_score(self, query_text: str, metadata: dict[str, Any]) -> float:
        field_name = str(metadata.get("field_name", ""))
        business_name = str(metadata.get("business_name", ""))
        canonical_name = str(metadata.get("canonical_name", ""))

        score = 1.0
        if field_name and field_name in query_text:
            score += 8.0
        if business_name and business_name in query_text:
            score += 8.0
        if canonical_name and canonical_name in query_text:
            score += 4.0
        if FIELD_WORD in query_text:
            score += 4.0

        field_boosts = [
            ("\u6838\u9500\u4eba\u6570", {"customer_id"}, 12.0),
            ("\u6838\u9500\u4eba\u6b21", {"verify_date_id"}, 12.0),
            ("\u6838\u9500\u5ba2\u5355\u4ef7", {"exe_income", "verify_date_id"}, 10.0),
            ("\u652f\u4ed8\u5ba2\u5355\u4ef7", {"pay_gmv", "uid", "stat_date", "pay_flag"}, 10.0),
            ("\u5f85\u6838\u9500", {"left_gmv", "left_num"}, 12.0),
            ("0\u5143", {"exe_income"}, 10.0),
            ("0 \u5143", {"exe_income"}, 10.0),
            ("\u95e8\u5e97", {"tenant_id", "sy_hospital_name"}, 8.0),
            ("\u5927\u533a", {"area_name"}, 8.0),
            ("\u57ce\u5e02", {"city_name"}, 8.0),
            ("\u6e20\u9053", {"cx_first_channel"}, 8.0),
            ("\u54c1\u9879", {"standard_name", "item_product_id"}, 8.0),
            ("\u6e17\u900f\u7387", {"standard_name", "customer_id"}, 8.0),
        ]
        for keyword, field_names, boost in field_boosts:
            if keyword in query_text and field_name in field_names:
                score += boost

        return score

    def _terms(self, text: str) -> list[str]:
        normalized = "".join(char for char in text if not char.isspace())
        terms = set(re.findall(r"[A-Za-z0-9_]+", normalized))
        terms.update(normalized[index:index + 2] for index in range(max(len(normalized) - 1, 0)))
        terms.update(normalized[index:index + 3] for index in range(max(len(normalized) - 2, 0)))
        return sorted(terms, key=len, reverse=True)
