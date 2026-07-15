import math
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any


_TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*|[\u4e00-\u9fff]{2,}|\d+")


def tokenize(text: str) -> list[str]:
    """Tokenize mixed Chinese / SQL identifier text for lightweight BM25."""
    tokens: list[str] = []
    for raw in _TOKEN_RE.findall(text.lower()):
        tokens.append(raw)
        if "_" in raw:
            tokens.extend(part for part in raw.split("_") if part)
        if re.fullmatch(r"[\u4e00-\u9fff]{3,}", raw):
            tokens.extend(
                raw[index:index + width]
                for width in (2, 3)
                for index in range(0, len(raw) - width + 1)
            )
    return tokens


@dataclass(frozen=True)
class BM25Document:
    id: str
    text: str
    payload: dict[str, Any] = field(default_factory=dict)


class BM25LexicalRetriever:
    """Small dependency-free BM25 retriever for schema/document lexical recall."""

    def __init__(
        self,
        documents: list[BM25Document],
        *,
        k1: float = 1.5,
        b: float = 0.75,
    ):
        self.documents = documents
        self.k1 = k1
        self.b = b
        self._doc_tokens = [tokenize(doc.text) for doc in documents]
        self._doc_lengths = [len(tokens) for tokens in self._doc_tokens]
        self._avg_doc_len = (
            sum(self._doc_lengths) / len(self._doc_lengths)
            if self._doc_lengths else 0.0
        )
        self._term_freqs = [Counter(tokens) for tokens in self._doc_tokens]
        self._doc_freqs = self._build_doc_freqs()

    def search(self, query: str, *, top_k: int = 20) -> list[dict[str, Any]]:
        query_terms = list(dict.fromkeys(tokenize(query)))
        if not query_terms or not self.documents:
            return []

        scored: list[dict[str, Any]] = []
        for index, doc in enumerate(self.documents):
            score = self._score(query_terms, index)
            if score <= 0:
                continue
            item = doc.payload.copy()
            item["id"] = doc.id
            item["bm25_score"] = score
            item["distance"] = 1.0 / (score + 1.0)
            item.setdefault("document", doc.text)
            scored.append(item)

        scored.sort(key=lambda item: (-item["bm25_score"], item["distance"], item["id"]))
        return scored[:top_k]

    def _build_doc_freqs(self) -> dict[str, int]:
        doc_freqs: dict[str, int] = {}
        for tokens in self._doc_tokens:
            for token in set(tokens):
                doc_freqs[token] = doc_freqs.get(token, 0) + 1
        return doc_freqs

    def _score(self, query_terms: list[str], doc_index: int) -> float:
        doc_len = self._doc_lengths[doc_index]
        if doc_len == 0 or self._avg_doc_len == 0:
            return 0.0

        term_freq = self._term_freqs[doc_index]
        doc_count = len(self.documents)
        score = 0.0
        for term in query_terms:
            freq = term_freq.get(term, 0)
            if freq == 0:
                continue
            doc_freq = self._doc_freqs.get(term, 0)
            idf = math.log(1.0 + (doc_count - doc_freq + 0.5) / (doc_freq + 0.5))
            denom = freq + self.k1 * (1.0 - self.b + self.b * doc_len / self._avg_doc_len)
            score += idf * (freq * (self.k1 + 1.0)) / denom
        return score
