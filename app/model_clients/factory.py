"""Provider factory — returns concrete clients based on Settings.

Default: local hash embedding + local lightweight rerank.
With DashScope: text-embedding-v4 + qwen3-rerank.

Pipeline calls create_embedding_client(settings) /
create_rerank_client(settings) instead of importing
concrete classes directly.
"""

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
        api_key = s.dashscope_api_key or s.llm_api_key
        if not api_key:
            raise RuntimeError(
                "EMBEDDING_PROVIDER=dashscope requires DASHSCOPE_API_KEY "
                "or LLM_API_KEY to be set."
            )
        return DashScopeEmbeddingClient(
            api_key=api_key,
            model=s.embedding_model or "text-embedding-v4",
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
        api_key = s.dashscope_api_key or s.llm_api_key
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
        )

    # default: local
    return LocalRerankClient()
