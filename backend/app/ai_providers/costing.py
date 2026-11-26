from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai_providers.models import AiModelPricing, FxRate

M = Decimal(1_000_000)


def get_pricing(db: Session, model_id, at: datetime) -> AiModelPricing | None:
    return db.scalar(select(AiModelPricing).where(
        AiModelPricing.model_id == model_id, AiModelPricing.effective_from <= at,
    ).order_by(AiModelPricing.effective_from.desc()))


def get_fx(db: Session, at: datetime, base="USD", quote="IDR") -> FxRate | None:
    return db.scalar(select(FxRate).where(
        FxRate.base == base, FxRate.quote == quote, FxRate.effective_from <= at,
    ).order_by(FxRate.effective_from.desc()))


def cost_usd(p: AiModelPricing, input_tokens: int, output_tokens: int, cached_tokens: int = 0) -> Decimal:
    cached = min(cached_tokens, input_tokens)
    cached_price = p.cached_input_per_1m if p.cached_input_per_1m is not None else p.input_per_1m
    return ((input_tokens - cached) * p.input_per_1m + cached * cached_price + output_tokens * p.output_per_1m) / M
