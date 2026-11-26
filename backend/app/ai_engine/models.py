import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin


class AiTool(Base, TimestampMixin):
    __tablename__ = "ai_tools"
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    name: Mapped[str] = mapped_column(String(150))
    category: Mapped[str] = mapped_column(String(40))  # planning|assessment|administration|analysis|media
    description: Mapped[str] = mapped_column(String(500), default="")
    input_schema: Mapped[dict] = mapped_column(JSON)
    output_schema: Mapped[dict] = mapped_column(JSON)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    est_input_tokens: Mapped[int] = mapped_column(default=1500)  # used for the pre-generation estimate
    est_output_tokens: Mapped[int] = mapped_column(default=2500)
    max_output_tokens: Mapped[int] = mapped_column(default=4000)
    sort: Mapped[int] = mapped_column(default=0)


class AiPromptVersion(Base, TimestampMixin):
    """Immutable once published; each request records the version it used."""

    __tablename__ = "ai_prompt_versions"
    __table_args__ = (UniqueConstraint("tool_id", "version"),)
    tool_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ai_tools.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column()
    system_prompt: Mapped[str] = mapped_column(Text)
    user_template: Mapped[str] = mapped_column(Text)  # Jinja (sandboxed)
    temperature: Mapped[Decimal] = mapped_column(Numeric(3, 2), default=Decimal("0.30"))
    status: Mapped[str] = mapped_column(String(10), default="draft")  # draft | published | archived
    change_note: Mapped[str] = mapped_column(String(300), default="")


class AiRequest(Base, TimestampMixin):
    __tablename__ = "ai_requests"
    __table_args__ = (UniqueConstraint("user_id", "idempotency_key"),)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    tool_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ai_tools.id"), index=True)
    prompt_version_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("ai_prompt_versions.id"))
    model_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("ai_models.id"))
    status: Mapped[str] = mapped_column(String(15), default="queued", index=True)  # queued|running|succeeded|failed
    idempotency_key: Mapped[str] = mapped_column(String(200))
    input: Mapped[dict] = mapped_column(JSON)
    output: Mapped[dict | None] = mapped_column(JSON)
    error_code: Mapped[str | None] = mapped_column(String(50))
    reservation_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("credit_reservations.id"))
    credits_reserved: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    credits_charged: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    attempts: Mapped[int] = mapped_column(default=0)
    target_document_id: Mapped[uuid.UUID | None] = mapped_column()  # no FK: avoids a documents<->ai_requests cycle  # set when regenerating a document
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AiUsage(Base, TimestampMixin):
    """Provider-reported usage, summed over every attempt of the request (incl. repair calls)."""

    __tablename__ = "ai_usage"
    request_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ai_requests.id", ondelete="CASCADE"), unique=True)
    provider_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("ai_providers.id"), index=True)
    model_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("ai_models.id"), index=True)
    input_tokens: Mapped[int] = mapped_column(default=0)
    output_tokens: Mapped[int] = mapped_column(default=0)
    cached_tokens: Mapped[int] = mapped_column(default=0)
    provider_request_id: Mapped[str] = mapped_column(String(100), default="")
    latency_ms: Mapped[int] = mapped_column(default=0)


class AiCostTracking(Base, TimestampMixin):
    """Owner's real API expense for the request. Separate from customer credits (credits_charged is only a link
    for margin reporting). is_estimate stays True until reconciled against the provider's invoice."""

    __tablename__ = "ai_cost_tracking"
    request_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ai_requests.id", ondelete="CASCADE"), unique=True)
    pricing_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("ai_model_pricing.id"))
    fx_rate_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("fx_rates.id"))
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    cost_idr: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    is_estimate: Mapped[bool] = mapped_column(Boolean, default=True)
    credits_charged: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    charge_mode: Mapped[str] = mapped_column(String(10), default="")
