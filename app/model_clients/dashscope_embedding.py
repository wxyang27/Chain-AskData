"""DashScope text-embedding-v4 client — OpenAI-compatible endpoint.

Usage:
    client = DashScopeEmbeddingClient(api_key="sk-xxx", model="text-embedding-v4")
    vectors = client.embed_texts(["核销收入", "exe_income"])
"""

import json
import math
import ssl
import urllib.error
import urllib.request

from app.model_clients.embedding_client import EmbeddingClient


def _l2_normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vec))
    if norm == 0:
        return vec
    return [v / norm for v in vec]


class DashScopeEmbeddingClient(EmbeddingClient):
    """DashScope text-embedding-v4 via OpenAI-compatible HTTP API."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str = "text-embedding-v4",
        dimension: int = 1024,
        base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings",
    ):
        self._api_key = api_key
        self._model = model
        self._dimension = dimension
        self._url = base_url.rstrip("/")

    BATCH_SIZE = 6  # DashScope text-embedding-v4 batch limit = 10; use 6 for safety

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        all_vectors: list[list[float]] = []
        for i in range(0, len(texts), self.BATCH_SIZE):
            batch = texts[i : i + self.BATCH_SIZE]
            vectors = self._embed_batch(batch)
            all_vectors.extend(vectors)
        return all_vectors

    def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        payload = {
            "model": self._model,
            "input": texts,
            "encoding_format": "float",
        }
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            url=self._url,
            data=data,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json; charset=utf-8",
            },
            method="POST",
        )
        ssl_context = ssl.create_default_context()

        try:
            with urllib.request.urlopen(request, timeout=60, context=ssl_context) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8")[:500]
            raise RuntimeError(f"DashScope embedding HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"DashScope embedding unreachable: {exc.reason}") from exc

        data_list = body.get("data", [])
        if not data_list:
            raise RuntimeError(f"DashScope embedding returned no data: {body}")

        return [
            _l2_normalize(entry["embedding"])
            for entry in sorted(data_list, key=lambda e: e.get("index", 0))
        ]

    def embed_query(self, query: str) -> list[float]:
        return self.embed_texts([query])[0]

    @property
    def dimension(self) -> int:
        return self._dimension
