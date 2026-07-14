"""DashScope rerank client — qwen3-rerank / qwen-rerank.

Usage:
    client = DashScopeRerankClient(api_key="sk-xxx", model="qwen3-rerank")
    results = client.rerank("核销收入", ["核销收入是指...", "支付GMV是指..."], top_n=5)
"""

import json
import ssl
import urllib.error
import urllib.request
from typing import Any

from app.model_clients.rerank_client import RerankClient


class DashScopeRerankClient(RerankClient):
    """DashScope qwen3-rerank / qwen-rerank via OpenAI-compatible HTTP API."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str = "qwen3-rerank",
        top_n: int = 20,
        workspace_id: str = "",
    ):
        self._api_key = api_key
        self._model = model
        self._top_n = top_n
        self._workspace_id = workspace_id

    def rerank(
        self,
        query: str,
        documents: list[str],
        top_n: int = 0,
    ) -> list[dict[str, Any]]:
        if not documents:
            return []

        n = top_n or self._top_n

        # DashScope rerank endpoint
        url = "https://dashscope.aliyuncs.com/api/v1/services/rerank/text-rerank/text-rerank"
        payload = {
            "model": self._model,
            "input": {
                "query": query,
                "documents": documents,
            },
            "parameters": {
                "top_n": min(n, len(documents)),
                "return_documents": False,
            },
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json; charset=utf-8",
        }
        if self._workspace_id:
            headers["X-DashScope-WorkSpace"] = self._workspace_id

        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(url, data=data, headers=headers, method="POST")
        ssl_context = ssl.create_default_context()

        try:
            with urllib.request.urlopen(request, timeout=30, context=ssl_context) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8")[:500]
            raise RuntimeError(f"DashScope rerank HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"DashScope rerank unreachable: {exc.reason}") from exc

        results = body.get("output", {}).get("results", [])
        return [
            {
                "document": documents[item.get("index", 0)],
                "score": item.get("relevance_score", 0.0),
                "index": item.get("index", 0),
            }
            for item in sorted(results, key=lambda r: r.get("index", 0))
        ]

    @property
    def provider_name(self) -> str:
        return f"dashscope/{self._model}"
