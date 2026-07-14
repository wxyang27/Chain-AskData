import os
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv()


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    """Application settings loaded from environment variables."""

    project_name: str = "Chain-AskData"

    llm_enabled: bool = _env_bool("LLM_ENABLED", False)
    llm_base_url: str = os.getenv("LLM_BASE_URL", "http://localhost:8000/v1")
    llm_api_key: str = os.getenv("LLM_API_KEY", "EMPTY")
    llm_cot_model: str = os.getenv("LLM_COT_MODEL", "qwen3.7-plus")
    llm_timeout_seconds: int = int(os.getenv("LLM_TIMEOUT_SECONDS", "60"))

    llm_keyword_model: str = os.getenv("LLM_KEYWORD_MODEL", "qwen")
    llm_sql_model: str = os.getenv("LLM_SQL_MODEL", "qwen-coder")
    llm_router_model: str = os.getenv("LLM_ROUTER_MODEL", "qwen-router")
    llm_validator_model: str = os.getenv("LLM_VALIDATOR_MODEL", "qwen-validator")
    llm_summary_model: str = os.getenv("LLM_SUMMARY_MODEL", "qwen-summary")

    embedding_enabled: bool = _env_bool("EMBEDDING_ENABLED", False)
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "qwen-embedding")

    rerank_enabled: bool = _env_bool("RERANK_ENABLED", False)
    rerank_url: str = os.getenv("RERANK_URL", "http://localhost:8001/rerank")

    # --- Pluggable model clients (local / dashscope) ---
    embedding_provider: str = os.getenv("EMBEDDING_PROVIDER", "local")
    embedding_dimension: int = int(os.getenv("EMBEDDING_DIMENSION", "128"))
    embedding_url: str = os.getenv(
        "EMBEDDING_URL",
        "https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings",
    )

    rerank_provider: str = os.getenv("RERANK_PROVIDER", "local")
    rerank_model: str = os.getenv("RERANK_MODEL", "lightweight")
    rerank_top_n: int = int(os.getenv("RERANK_TOP_N", "20"))

    dashscope_api_key: str = os.getenv("DASHSCOPE_API_KEY", "")
    dashscope_workspace_id: str = os.getenv("DASHSCOPE_WORKSPACE_ID", "")


settings = Settings()
