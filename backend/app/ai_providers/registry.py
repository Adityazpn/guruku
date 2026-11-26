import os

from app.ai_providers.adapters.fake import FakeProvider
from app.ai_providers.adapters.openai import OpenAIAdapter
from app.ai_providers.base import ProviderBadRequest
from app.ai_providers.models import AiProvider, AiProviderCredential
from app.core.crypto import decrypt_secret

# Anthropic / Gemini adapters are planned (optional providers); until then they cannot be enabled.
ADAPTERS = {"openai": OpenAIAdapter, "fake": FakeProvider}


def resolve_api_key(db, provider: AiProvider) -> tuple[str, AiProviderCredential | None]:
    """DB credential (encrypted) first, env var `<CODE>_API_KEY` as bootstrap fallback. Never logged."""
    from sqlalchemy import select

    cred = db.scalar(select(AiProviderCredential).where(
        AiProviderCredential.provider_id == provider.id, AiProviderCredential.status == "active"
    ).order_by(AiProviderCredential.created_at.desc()))
    if cred:
        return decrypt_secret(cred.secret_ciphertext), cred
    return os.environ.get(f"{provider.code.upper()}_API_KEY", ""), None


def build_adapter(provider: AiProvider, api_key: str):
    cls = ADAPTERS.get(provider.code)
    if cls is None:
        raise ProviderBadRequest(f"no adapter for provider '{provider.code}'")
    return cls(api_key, base_url=provider.base_url) if cls is OpenAIAdapter else cls(api_key)
