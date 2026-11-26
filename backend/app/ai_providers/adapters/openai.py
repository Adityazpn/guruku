"""OpenAI Chat Completions adapter.

NOT yet verified against the live API (no key available in development). Before enabling in production:
check the current OpenAI docs for the model id, the token-limit parameter name, JSON-mode support and
usage fields, and run the opt-in live smoke test. HTTP behaviour is covered by mock-transport tests.
"""
import httpx

from app.ai_providers.base import (
    LLMRequest,
    LLMResponse,
    ProviderAuthError,
    ProviderBadRequest,
    ProviderError,
    ProviderQuotaExhausted,
    ProviderRateLimited,
    ProviderTimeout,
    ProviderUnavailable,
)


class OpenAIAdapter:
    code = "openai"

    def __init__(self, api_key: str, base_url: str | None = None, client: httpx.Client | None = None):
        self._key = api_key
        self._base = (base_url or "https://api.openai.com/v1").rstrip("/")
        self._client = client or httpx.Client()

    def generate(self, req: LLMRequest) -> LLMResponse:
        body = {
            "model": req.model,
            "messages": [{"role": "system", "content": req.system}, {"role": "user", "content": req.user}],
            "max_completion_tokens": req.max_tokens,
            "temperature": req.temperature,
        }
        if req.json_mode:
            body["response_format"] = {"type": "json_object"}
        try:
            r = self._client.post(f"{self._base}/chat/completions", json=body, timeout=req.timeout_s,
                                  headers={"Authorization": f"Bearer {self._key}"})
        except httpx.TimeoutException as e:
            raise ProviderTimeout(str(e)) from e
        except httpx.HTTPError as e:
            raise ProviderUnavailable(str(e)) from e
        if r.status_code != 200:
            self._raise(r)
        d = r.json()
        try:
            choice = d["choices"][0]
            usage = d.get("usage", {})
            return LLMResponse(
                text=choice["message"]["content"] or "",
                input_tokens=int(usage.get("prompt_tokens", 0)),
                output_tokens=int(usage.get("completion_tokens", 0)),
                cached_tokens=int((usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0) or 0),
                provider_request_id=d.get("id", ""),
                finish_reason=choice.get("finish_reason", ""),
            )
        except (KeyError, IndexError, TypeError) as e:
            raise ProviderUnavailable("unexpected response shape") from e

    @staticmethod
    def _raise(r: httpx.Response):
        try:
            err = r.json().get("error", {})
        except ValueError:
            err = {}
        code = (err.get("code") or err.get("type") or "") if isinstance(err, dict) else ""
        msg = f"{r.status_code} {code}"
        if r.status_code in (401, 403):
            raise ProviderAuthError(msg)
        if r.status_code == 429:
            if "quota" in code or "billing" in code:
                raise ProviderQuotaExhausted(msg)
            raise ProviderRateLimited(msg)
        if r.status_code in (400, 404, 422):
            raise ProviderBadRequest(msg)
        if r.status_code >= 500:
            raise ProviderUnavailable(msg)
        raise ProviderError(msg)
