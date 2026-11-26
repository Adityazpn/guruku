"""Deterministic provider for development and tests. Behaviour is scripted per call via `script`."""
import json

from app.ai_providers.base import LLMRequest, LLMResponse


class FakeProvider:
    code = "fake"
    script: list = []  # items: Exception to raise, str to return as text, or LLMResponse
    calls: list[LLMRequest] = []

    def __init__(self, api_key: str = "", **_):
        pass

    def generate(self, req: LLMRequest) -> LLMResponse:
        FakeProvider.calls.append(req)
        item = FakeProvider.script.pop(0) if FakeProvider.script else json.dumps({"ok": True})
        if isinstance(item, Exception):
            raise item
        if isinstance(item, LLMResponse):
            return item
        return LLMResponse(text=item, input_tokens=1000, output_tokens=2000, provider_request_id="fake-1",
                           finish_reason="stop")
