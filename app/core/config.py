import os
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv()


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return int(value)


def _default_embedding_dimension() -> int:
    provider = os.getenv("EMBEDDING_PROVIDER", "local").strip().lower()
    return 1024 if provider == "dashscope" else 128


@dataclass(frozen=True)
class Settings:
    """Application settings loaded from environment variables."""

    project_name: str = "Chain-AskData"

    llm_enabled: bool = _env_bool("LLM_ENABLED", False)
    llm_base_url: str = os.getenv("LLM_BASE_URL", "http://localhost:8000/v1")
    llm_api_key: str = os.getenv("LLM_API_KEY", "EMPTY")
    # Model role split: planning can use a thinking model, SQL generation can use a coder model.
    llm_cot_model: str = os.getenv(
        "LLM_THINKING_MODEL",
        os.getenv("LLM_COT_MODEL", "qwen-plus"),
    )
    llm_timeout_seconds: int = int(os.getenv("LLM_TIMEOUT_SECONDS", "60"))

    llm_keyword_model: str = os.getenv("LLM_KEYWORD_MODEL", "qwen")
    llm_sql_model: str = os.getenv(
        "LLM_CODER_MODEL",
        os.getenv("LLM_SQL_MODEL", "qwen-plus"),
    )
    llm_router_model: str = os.getenv("LLM_ROUTER_MODEL", "qwen-router")
    llm_validator_model: str = os.getenv("LLM_VALIDATOR_MODEL", "qwen-validator")
    llm_summary_model: str = os.getenv("LLM_SUMMARY_MODEL", "qwen-summary")

    embedding_enabled: bool = _env_bool("EMBEDDING_ENABLED", False)
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "qwen-embedding")

    rerank_enabled: bool = _env_bool("RERANK_ENABLED", False)
    rerank_url: str = os.getenv("RERANK_URL", "")

    # --- Pluggable model clients (local / dashscope) ---
    embedding_provider: str = os.getenv("EMBEDDING_PROVIDER", "local")
    embedding_dimension: int = _env_int("EMBEDDING_DIMENSION", _default_embedding_dimension())
    embedding_url: str = os.getenv(
        "EMBEDDING_URL",
        "https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings",
    )

    rerank_provider: str = os.getenv("RERANK_PROVIDER", "local")
    rerank_model: str = os.getenv("RERANK_MODEL", "lightweight")
    rerank_top_n: int = _env_int("RERANK_TOP_N", 20)
    rerank_endpoint_mode: str = os.getenv("RERANK_ENDPOINT_MODE", "auto")

    dashscope_api_key: str = os.getenv("DASHSCOPE_API_KEY", "")
    dashscope_workspace_id: str = os.getenv("DASHSCOPE_WORKSPACE_ID", "")

    # --- SQL execution layer ---
    # disabled: default, stable for demos/tests; no SQL is executed.
    # mock: dry-run executor returns deterministic sample rows.
    # sqlite: executes against a local SQLite demo database.
    execution_mode: str = os.getenv("EXECUTION_MODE", "disabled")
    execution_timeout_seconds: int = _env_int("EXECUTION_TIMEOUT_SECONDS", 30)
    execution_max_rows: int = _env_int("EXECUTION_MAX_ROWS", 100)
    execution_sqlite_path: str = os.getenv("EXECUTION_SQLITE_PATH", "runtime_data/trade_demo.db")
    odps_access_id: str = os.getenv("ODPS_ACCESS_ID", os.getenv("MAXCOMPUTE_ACCESS_ID", ""))
    odps_secret_access_key: str = os.getenv(
        "ODPS_SECRET_ACCESS_KEY",
        os.getenv("MAXCOMPUTE_SECRET_ACCESS_KEY", ""),
    )
    odps_project_name: str = os.getenv("ODPS_PROJECT_NAME", os.getenv("MAXCOMPUTE_PROJECT", "soyoung_dw"))
    odps_endpoint: str = os.getenv(
        "ODPS_ENDPOINT",
        os.getenv("MAXCOMPUTE_ENDPOINT", "http://service.cn-beijing.maxcompute.aliyun.com/api"),
    )
    odps_logview_host: str = os.getenv("ODPS_LOGVIEW_HOST", "")

    # --- Feishu / Lark bot long-connection entry ---
    feishu_app_id: str = os.getenv("FEISHU_APP_ID", os.getenv("LARK_APP_ID", ""))
    feishu_app_secret: str = os.getenv("FEISHU_APP_SECRET", os.getenv("LARK_APP_SECRET", ""))
    feishu_verification_token: str = os.getenv("FEISHU_VERIFICATION_TOKEN", "")
    feishu_encrypt_key: str = os.getenv("FEISHU_ENCRYPT_KEY", "")
    feishu_reply_enabled: bool = _env_bool("FEISHU_REPLY_ENABLED", True)
    feishu_max_reply_chars: int = _env_int("FEISHU_MAX_REPLY_CHARS", 3500)
    feishu_group_require_mention: bool = _env_bool("FEISHU_GROUP_REQUIRE_MENTION", True)
    feishu_raw_event_log: bool = _env_bool("FEISHU_RAW_EVENT_LOG", False)
    feishu_include_sql: bool = _env_bool("FEISHU_INCLUDE_SQL", False)
    feishu_card_enabled: bool = _env_bool("FEISHU_CARD_ENABLED", True)
    feishu_memory_enabled: bool = _env_bool("FEISHU_MEMORY_ENABLED", True)
    feishu_llm_enabled: bool = _env_bool("FEISHU_LLM_ENABLED", False)
    feishu_execution_mode: str = os.getenv("FEISHU_EXECUTION_MODE", "disabled")
    feishu_log_enabled: bool = _env_bool("FEISHU_LOG_ENABLED", True)
    feishu_log_base_token: str = os.getenv("FEISHU_LOG_BASE_TOKEN", "")
    feishu_log_table_id: str = os.getenv("FEISHU_LOG_TABLE_ID", "")
    feishu_log_cli: str = os.getenv("FEISHU_LOG_CLI", "lark-cli")
    feishu_log_identity: str = os.getenv("FEISHU_LOG_IDENTITY", "user")


settings = Settings()
