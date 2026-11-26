from dataclasses import dataclass
from typing import Protocol


class ProviderError(Exception):
    code = "provider_error"
    retryable = False  # same model may be retried
    failover = True  # another model/provider may be tried


class ProviderTimeout(ProviderError):
    code, retryable = "provider_timeout", True


class ProviderRateLimited(ProviderError):
    code, retryable = "provider_rate_limited", True


class ProviderUnavailable(ProviderError):
    code, retryable = "provider_unavailable", True


class ProviderAuthError(ProviderError):
    code = "provider_auth"


class ProviderQuotaExhausted(ProviderError):
    code = "provider_quota"


class ProviderBadRequest(ProviderError):
    code = "provider_bad_request"


class MalformedOutput(ProviderError):
    code = "malformed_output"
    failover = False


@dataclass
class LLMRequest:
    model: str
    system: str
    user: str
    max_tokens: int
    temperature: float = 0.3
    json_mode: bool = True
    timeout_s: float = 90.0


@dataclass
class LLMResponse:
    text: str
    input_tokens: int
    output_tokens: int
    cached_tokens: int = 0
    provider_request_id: str = ""
    finish_reason: str = ""


class LLMProvider(Protocol):
    code: str

    def generate(self, req: LLMRequest) -> LLMResponse: ...
