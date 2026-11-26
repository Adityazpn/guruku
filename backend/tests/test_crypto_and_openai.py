import httpx
import pytest

from app.ai_providers.adapters.openai import OpenAIAdapter
from app.ai_providers.base import (
    LLMRequest,
    ProviderAuthError,
    ProviderBadRequest,
    ProviderQuotaExhausted,
    ProviderRateLimited,
    ProviderTimeout,
    ProviderUnavailable,
)
from app.core import config, crypto

REQ = LLMRequest(model="m-1", system="sys", user="usr", max_tokens=100)


@pytest.fixture
def master(monkeypatch):
    monkeypatch.setenv("PROVIDER_KEY_MASTER", "test-master-key")
    config.get_settings.cache_clear()
    yield
    config.get_settings.cache_clear()


def test_crypto_roundtrip(master):
    ct = crypto.encrypt_secret("sk-secret-123")
    assert "sk-secret" not in ct and crypto.decrypt_secret(ct) == "sk-secret-123"


def test_crypto_refuses_without_master(monkeypatch):
    monkeypatch.delenv("PROVIDER_KEY_MASTER", raising=False)
    monkeypatch.setattr(config, "get_settings", lambda: config.Settings(provider_key_master="", _env_file=None))
    monkeypatch.setattr(crypto, "get_settings", config.get_settings)
    with pytest.raises(RuntimeError):
        crypto.encrypt_secret("x")


def test_wrong_master_cannot_decrypt(monkeypatch, master):
    ct = crypto.encrypt_secret("k")
    monkeypatch.setenv("PROVIDER_KEY_MASTER", "other")
    config.get_settings.cache_clear()
    with pytest.raises(RuntimeError):
        crypto.decrypt_secret(ct)


def adapter(handler):
    return OpenAIAdapter("sk-test-KEY", client=httpx.Client(transport=httpx.MockTransport(handler)))


def test_openai_success_maps_usage_and_sends_auth():
    seen = {}

    def h(request: httpx.Request):
        seen["auth"], seen["body"] = request.headers["authorization"], request.read().decode()
        return httpx.Response(200, json={
            "id": "chatcmpl-1", "choices": [{"message": {"content": "{}"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 12, "completion_tokens": 34, "prompt_tokens_details": {"cached_tokens": 5}}})

    r = adapter(h).generate(REQ)
    assert (r.input_tokens, r.output_tokens, r.cached_tokens, r.provider_request_id) == (12, 34, 5, "chatcmpl-1")
    assert seen["auth"] == "Bearer sk-test-KEY" and '"json_object"' in seen["body"] and '"m-1"' in seen["body"]


@pytest.mark.parametrize("status,body,exc", [
    (401, {"error": {"code": "invalid_api_key"}}, ProviderAuthError),
    (429, {"error": {"code": "insufficient_quota"}}, ProviderQuotaExhausted),
    (429, {"error": {"code": "rate_limit_exceeded"}}, ProviderRateLimited),
    (400, {"error": {"code": "bad"}}, ProviderBadRequest),
    (503, {}, ProviderUnavailable),
])
def test_openai_error_mapping_and_no_key_leak(status, body, exc):
    with pytest.raises(exc) as e:
        adapter(lambda r: httpx.Response(status, json=body)).generate(REQ)
    assert "sk-test-KEY" not in str(e.value)


def test_openai_timeout_and_network():
    def boom(request):
        raise httpx.ReadTimeout("slow")

    with pytest.raises(ProviderTimeout):
        adapter(boom).generate(REQ)

    def down(request):
        raise httpx.ConnectError("no route")

    with pytest.raises(ProviderUnavailable):
        adapter(down).generate(REQ)
