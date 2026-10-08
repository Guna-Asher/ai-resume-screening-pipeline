"""OpenRouter adapter. The only module that knows OpenRouter's request/response shapes."""
import base64
import os
from collections.abc import Mapping

import httpx

from .base import ImagePart, LLMError

BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "anthropic/claude-sonnet-4.6"
REQUEST_TIMEOUT_S = 90.0   # vision + JSON output on a full resume page set
MAX_OUTPUT_TOKENS = 8000


class OpenRouterClient:
    def __init__(self, api_key: str, model: str = DEFAULT_MODEL, *, timeout: float = REQUEST_TIMEOUT_S,
                 base_url: str = BASE_URL, http: httpx.Client | None = None):
        if not api_key:
            raise ValueError("OpenRouter API key is required")
        self._api_key = api_key
        self.model = model
        self.timeout = timeout
        self._url = f"{base_url.rstrip('/')}/chat/completions"
        self._http = http or httpx.Client()

    def __repr__(self) -> str:  # never expose the key
        return f"OpenRouterClient(model={self.model!r})"

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "OpenRouterClient | None":
        """None when OPENROUTER_API_KEY is unset/empty (LLM fallback is then unavailable)."""
        env = os.environ if environ is None else environ
        key = (env.get("OPENROUTER_API_KEY") or "").strip()
        if not key:
            return None
        return cls(key, (env.get("OPENROUTER_MODEL") or "").strip() or DEFAULT_MODEL)

    def complete_json(self, *, system: str, user_text: str, images: list[ImagePart],
                      schema_name: str, schema: dict) -> str:
        content: list[dict] = [{"type": "text", "text": user_text}]
        for img in images:
            b64 = base64.b64encode(img.data).decode("ascii")
            content.append({"type": "image_url", "image_url": {"url": f"data:{img.mime};base64,{b64}"}})
        body = {
            "model": self.model,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": content}],
            "response_format": {"type": "json_schema",
                                "json_schema": {"name": schema_name, "strict": True, "schema": schema}},
            "provider": {"require_parameters": True},  # only route to providers that honour the schema
            "temperature": 0,
            "max_tokens": MAX_OUTPUT_TOKENS,
        }
        headers = {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}
        try:
            resp = self._http.post(self._url, json=body, headers=headers, timeout=self.timeout)
        except httpx.TimeoutException:
            raise LLMError(f"OpenRouter request timed out after {self.timeout:g}s") from None
        except httpx.HTTPError as e:
            raise LLMError(f"OpenRouter network error: {type(e).__name__}") from None

        if resp.status_code != 200:
            raise LLMError(f"OpenRouter HTTP {resp.status_code}: {_error_message(resp)}")
        try:
            data = resp.json()
        except ValueError:
            raise LLMError("OpenRouter returned a non-JSON response") from None
        if isinstance(data, dict) and data.get("error"):
            raise LLMError(f"OpenRouter error: {_short(data['error'])}")
        try:
            return data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError):
            raise LLMError("OpenRouter response had no choices[0].message.content") from None


def _short(value, limit: int = 200) -> str:
    if isinstance(value, dict):
        value = value.get("message", value)
    return str(value)[:limit]


def _error_message(resp: httpx.Response) -> str:
    try:
        return _short(resp.json().get("error", resp.text))
    except (ValueError, AttributeError):
        return resp.text[:200]
