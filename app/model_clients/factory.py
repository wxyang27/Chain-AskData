"""Provider factory — returns concrete clients based on Settings.

Default: local hash embedding + local lightweight rerank.
With DashScope: text-embedding-v4 + qwen3-rerank.

Pipeline calls create_embedding_client(settings) /
create_rerank_client(settings) instead of importing
concrete classes directly.
"""

import os

from app.core.config import Settings
from app.model_clients.embedding_client import EmbeddingClient
from app.model_clients.local_embedding import LocalHashEmbeddingClient
from app.model_clients.local_rerank import LocalRerankClient
from app.model_clients.rerank_client import RerankClient


def create_embedding_client(settings: Settings | None = None) -> EmbeddingClient:
    """Create the configured embedding client."""
    from app.core.config import settings as _settings
    s = settings or _settings

    provider = s.embedding_provider

    if provider == "dashscope":
        try:
            from app.model_clients.dashscope_embedding import DashScopeEmbeddingClient
        except ImportError:
            raise RuntimeError(
                "EMBEDDING_PROVIDER=dashscope but DashScopeEmbeddingClient "
                "is not available. Make sure dashscope_embedding.py exists."
            )
        api_key = _usable_api_key(s.dashscope_api_key) or _usable_api_key(s.llm_api_key)
        if not api_key:
            raise RuntimeError(
                "EMBEDDING_PROVIDER=dashscope requires DASHSCOPE_API_KEY "
                "or LLM_API_KEY to be set."
            )
        return DashScopeEmbeddingClient(
            api_key=api_key,
            model=_dashscope_embedding_model(s),
            dimension=s.embedding_dimension or 1024,
            base_url=s.embedding_url,
        )

    # default: local
    return LocalHashEmbeddingClient(dimension=s.embedding_dimension or 128)


def create_rerank_client(settings: Settings | None = None) -> RerankClient:
    """Create the configured rerank client."""
    from app.core.config import settings as _settings
    s = settings or _settings

    provider = s.rerank_provider

    if provider == "dashscope":
        try:
            from app.model_clients.dashscope_rerank import DashScopeRerankClient
        except ImportError:
            raise RuntimeError(
                "RERANK_PROVIDER=dashscope but DashScopeRerankClient "
                "is not available."
            )
        api_key = _usable_api_key(s.dashscope_api_key) or _usable_api_key(s.llm_api_key)
        if not api_key:
            raise RuntimeError(
                "RERANK_PROVIDER=dashscope requires DASHSCOPE_API_KEY "
                "or LLM_API_KEY to be set."
            )
        return DashScopeRerankClient(
            api_key=api_key,
            model=s.rerank_model or "qwen3-rerank",
            top_n=s.rerank_top_n,
            workspace_id=s.dashscope_workspace_id,
            base_url=s.rerank_url,
            endpoint_mode=s.rerank_endpoint_mode,
        )

    # default: local
    return LocalRerankClient()


def _dashscope_embedding_model(settings: Settings) -> str:
    if os.getenv("EMBEDDING_MODEL") and settings.embedding_model != "qwen-embedding":
        return settings.embedding_model
    return "text-embedding-v4"


def _usable_api_key(value: str) -> str:
    normalized = (value or "").strip()
    if normalized.upper() in {"", "EMPTY", "NONE", "NULL"}:
        return ""
    return normalized
