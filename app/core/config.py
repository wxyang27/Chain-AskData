import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    """应用配置。真实密钥通过本地 .env 或环境变量注入。"""

    project_name: str = "Chain-AskData"
    llm_provider: str = os.getenv("LLM_PROVIDER", "deepseek")
    deepseek_api_key: str = os.getenv("DEEPSEEK_API_KEY", "")
    deepseek_base_url: str = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    deepseek_model: str = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")


settings = Settings()
