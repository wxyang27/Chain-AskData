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
        base_url: str = "",
        endpoint_mode: str = "auto",
    ):
        self._api_key = api_key
        self._model = model
        self._top_n = top_n
        self._workspace_id = workspace_id
        self._endpoint_mode = endpoint_mode
        self._url = base_url or self._default_url()

    def rerank(
        self,
        query: str,
        documents: list[str],
        top_n: int = 0,
    ) -> list[dict[str, Any]]:
        if not documents:
            return []

        n = top_n or self._top_n

        url = self._url
        payload = self._payload(query, documents, min(n, len(documents)))
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json; charset=utf-8",
        }
        if self._workspace_id and not self._is_compatible_endpoint():
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

        results = self._extract_results(body)
        return [
            {
                "document": documents[item.get("index", 0)],
                "score": item.get("relevance_score", 0.0),
                "index": item.get("index", 0),
            }
            for item in sorted(results, key=lambda r: r.get("relevance_score", 0.0), reverse=True)
        ]

    @property
    def provider_name(self) -> str:
        return f"dashscope/{self._model}"

    def _default_url(self) -> str:
        if self._workspace_id:
            return (
                f"https://{self._workspace_id}.cn-beijing.maas.aliyuncs.com"
                "/compatible-api/v1/reranks"
            )
        return "https://dashscope.aliyuncs.com/api/v1/services/rerank/text-rerank/text-rerank"

    def _is_compatible_endpoint(self) -> bool:
        if self._endpoint_mode == "compatible":
            return True
        if self._endpoint_mode == "dashscope":
            return False
        return "compatible-api/v1/reranks" in self._url

    def _payload(self, query: str, documents: list[str], top_n: int) -> dict[str, Any]:
        if self._is_compatible_endpoint():
            return {
                "model": self._model,
                "query": query,
                "documents": documents,
                "top_n": top_n,
            }
        return {
            "model": self._model,
            "input": {
                "query": query,
                "documents": documents,
            },
            "parameters": {
                "top_n": top_n,
                "return_documents": False,
            },
        }

    def _extract_results(self, body: dict[str, Any]) -> list[dict[str, Any]]:
        if self._is_compatible_endpoint():
            return body.get("results", [])
        return body.get("output", {}).get("results", [])
