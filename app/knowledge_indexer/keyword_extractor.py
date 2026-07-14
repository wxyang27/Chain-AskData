import re


class KeywordExtractor:
    """Small deterministic keyword extractor for AskData-lite retrieval."""

    BUSINESS_TERMS = [
        "\u6838\u9500\u4eba\u6570",
        "\u6838\u9500\u4eba\u6b21",
        "\u6838\u9500\u6536\u5165",
        "\u6838\u9500GMV",
        "\u6838\u9500\u5ba2\u5355\u4ef7",
        "\u652f\u4ed8GMV",
        "\u652f\u4ed8\u5ba2\u5355\u4ef7",
        "\u5f85\u6838\u9500\u91d1\u989d",
        "\u5f85\u6838\u9500",
        "\u95e8\u5e97",
        "\u54c1\u9879",
        "\u54c1\u7c7b",
        "\u5927\u5355\u54c1",
        "\u5e38\u89c4\u54c1",
        "\u5927\u5e08\u56e2",
        "\u6536\u5165\u5206\u7c7b",
        "revenue_category",
        "\u6e20\u9053",
        "\u65b0\u5ba2",
        "\u8001\u5ba2",
    ]

    def extract(self, query_text: str) -> list[str]:
        keywords = []
        for term in self.BUSINESS_TERMS:
            if term in query_text:
                keywords.append(term)

        keywords.extend(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", query_text))

        if "\u5b57\u6bb5" in query_text:
            keywords.append("\u5b57\u6bb5")
        if "\u53e3\u5f84" in query_text:
            keywords.append("\u53e3\u5f84")

        return list(dict.fromkeys(keywords))
