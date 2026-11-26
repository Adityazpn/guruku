from decimal import Decimal

from sqlalchemy import Boolean, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin
from app.credits.pricing import PricingRule


class CreditPricingRule(Base, TimestampMixin):
    """Per-tool credit pricing; tool_slug NULL = global default. Admin-editable, versioned."""

    __tablename__ = "credit_pricing_rules"
    tool_slug: Mapped[str | None] = mapped_column(String(80), index=True)
    version: Mapped[int] = mapped_column(default=1)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    mode: Mapped[str] = mapped_column(String(10), default="fixed")
    fixed_credits: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=1)
    base_credits: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    margin_pct: Mapped[Decimal] = mapped_column(Numeric(8, 2), default=300)
    processing_fee_idr: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    credit_value_idr: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=250)
    rounding_step: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=Decimal("0.5"))
    min_credits: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=1)
    max_credits: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=20)
    reserve_safety_factor: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=Decimal("1.3"))

    def to_rule(self) -> PricingRule:
        return PricingRule(
            mode=self.mode, fixed_credits=Decimal(self.fixed_credits), base_credits=Decimal(self.base_credits),
            margin_pct=Decimal(self.margin_pct), processing_fee_idr=Decimal(self.processing_fee_idr),
            credit_value_idr=Decimal(self.credit_value_idr), rounding_step=Decimal(self.rounding_step),
            min_credits=Decimal(self.min_credits), max_credits=Decimal(self.max_credits),
            reserve_safety_factor=Decimal(self.reserve_safety_factor))
