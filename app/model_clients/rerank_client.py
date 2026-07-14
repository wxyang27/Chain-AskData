"""Rerank client interface.

Current default: LightweightReranker (lexical, deterministic).
Future: DashScope qwen-rerank or qwen3-rerank (neural, cross-encoder).
"""

from abc import ABC, abstractmethod
from typing import Any


class RerankClient(ABC):
    """Abstract rerank provider.

    Concrete implementations:
        LightweightReranker  — lexical, keyword/field/term weighted
        DashScopeRerank      — neural, qwen-rerank / qwen3-rerank
    """

    @abstractmethod
    def rerank(
        self,
        query: str,
        documents: list[str],
        top_n: int,
    ) -> list[dict[str, Any]]:
        """Rerank documents against query, returning top_n with scores.

        Returns:
            List of dicts with keys: ``document``, ``score``, ``index``.
        """
        ...

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Human-readable provider name for tracing."""
        ...
