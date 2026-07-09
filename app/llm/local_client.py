import json
import ssl
import urllib.error
import urllib.request
from typing import Any


class LocalLLMClient:
    """Minimal OpenAI-compatible chat client for local/cloud Qwen deployments."""

    def __init__(
        self,
        base_url: str = "http://localhost:8000/v1",
        api_key: str = "EMPTY",
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    def chat_json(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        temperature: float = 0,
        timeout_seconds: int = 30,
    ) -> dict[str, Any]:
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "response_format": {"type": "json_object"},
        }
        data_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")

        request = urllib.request.Request(
            url=f"{self.base_url}/chat/completions",
            data=data_bytes,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json; charset=utf-8",
            },
            method="POST",
        )

        ssl_context = ssl.create_default_context()

        try:
            with urllib.request.urlopen(
                request, timeout=timeout_seconds, context=ssl_context
            ) as response:
                response_payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = ""
            try:
                body = exc.read().decode("utf-8")[:500]
            except Exception:
                pass
            raise RuntimeError(
                f"LLM HTTP {exc.code}: {body}"
            ) from exc
        except urllib.error.URLError as exc:
            reason = str(exc.reason) if exc.reason else str(exc)
            raise RuntimeError(f"LLM request failed: {reason}") from exc

        content = (
            response_payload.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
        )
        if not content:
            raise ValueError("LLM response did not include message content")

        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            raise ValueError(f"LLM response is not valid JSON: {content[:200]}") from exc
