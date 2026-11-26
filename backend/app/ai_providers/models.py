import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin


class AiProvider(Base, TimestampMixin):
    __tablename__ = "ai_providers"
    code: Mapped[str] = mapped_column(String(30), unique=True)  # openai | anthropic | google | fake
    name: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(10), default="disabled")  # enabled | disabled
    base_url: Mapped[str | None] = mapped_column(String(300))
    daily_spend_limit_usd: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    monthly_spend_limit_usd: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))


class AiProviderCredential(Base, TimestampMixin):
    """API key stored encrypted; never returned by any endpoint (only last4)."""

    __tablename__ = "ai_provider_credentials"
    provider_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ai_providers.id", ondelete="CASCADE"), index=True)
    label: Mapped[str] = mapped_column(String(100), default="")
    secret_ciphertext: Mapped[str] = mapped_column(String(1000))
    key_id: Mapped[str] = mapped_column(String(10), default="v1")
    last4: Mapped[str] = mapped_column(String(4), default="")
    status: Mapped[str] = mapped_column(String(10), default="active")  # active | invalid | revoked


class AiModel(Base, TimestampMixin):
    __tablename__ = "ai_models"
    __table_args__ = (UniqueConstraint("provider_id", "model_code"),)
    provider_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ai_providers.id", ondelete="CASCADE"), index=True)
    model_code: Mapped[str] = mapped_column(String(100))
    display_name: Mapped[str] = mapped_column(String(100), default="")
    status: Mapped[str] = mapped_column(String(10), default="active")  # active | disabled
    max_output_tokens: Mapped[int] = mapped_column(default=4096)


class AiModelPricing(Base, TimestampMixin):
    """Provider price per 1M tokens, in `currency` (USD). Versioned by effective date; never hardcoded."""

    __tablename__ = "ai_model_pricing"
    model_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ai_models.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(default=1)
    input_per_1m: Mapped[Decimal] = mapped_column(Numeric(14, 6))
    output_per_1m: Mapped[Decimal] = mapped_column(Numeric(14, 6))
    cached_input_per_1m: Mapped[Decimal | None] = mapped_column(Numeric(14, 6))
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class FxRate(Base, TimestampMixin):
    __tablename__ = "fx_rates"
    base: Mapped[str] = mapped_column(String(3), default="USD")
    quote: Mapped[str] = mapped_column(String(3), default="IDR")
    rate: Mapped[Decimal] = mapped_column(Numeric(14, 4))
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AiToolModelAssignment(Base, TimestampMixin):
    __tablename__ = "ai_tool_model_assignments"
    __table_args__ = (UniqueConstraint("tool_id", "model_id"),)
    tool_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ai_tools.id", ondelete="CASCADE"), index=True)
    model_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ai_models.id", ondelete="CASCADE"))
    priority: Mapped[int] = mapped_column(default=0)  # lower = tried first; later ones act as fallbacks
