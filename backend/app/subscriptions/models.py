import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Numeric, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin


class Plan(Base, TimestampMixin):
    __tablename__ = "plans"
    code: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(String(500), default="")
    credits_monthly: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    features: Mapped[list] = mapped_column(JSON, default=list)  # display bullets
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort: Mapped[int] = mapped_column(default=0)


class PlanPrice(Base, TimestampMixin):
    __tablename__ = "plan_prices"
    plan_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("plans.id", ondelete="CASCADE"), index=True)
    cycle: Mapped[str] = mapped_column(String(10))  # monthly | annual
    amount_idr: Mapped[int] = mapped_column()
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Subscription(Base, TimestampMixin):
    __tablename__ = "subscriptions"
    __table_args__ = (Index("uq_one_live_subscription", "user_id", unique=True,
                            postgresql_where=text("status IN ('active','past_due')"), sqlite_where=text("status IN ('active','past_due')")),)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    plan_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("plans.id"))
    cycle: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(12), default="active")  # active | past_due | canceled | expired
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    months_paid: Mapped[int] = mapped_column(default=1)  # period_end = period_start + months_paid months
    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, default=False)
    grace_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CreditPackage(Base, TimestampMixin):
    __tablename__ = "credit_packages"
    name: Mapped[str] = mapped_column(String(100))
    credits: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    price_idr: Mapped[int] = mapped_column()
    bonus_credits: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    bonus_expiry_days: Mapped[int] = mapped_column(default=30)
    purchased_expiry_days: Mapped[int | None] = mapped_column()  # None = never expires
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort: Mapped[int] = mapped_column(default=0)
