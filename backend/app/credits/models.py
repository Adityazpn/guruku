import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import JSON, DateTime, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin, utcnow

AMOUNT = Numeric(12, 2)


class BucketType(str, enum.Enum):
    subscription = "subscription"
    bonus = "bonus"
    purchased = "purchased"


class TxType(str, enum.Enum):
    subscription_allocation = "subscription_allocation"
    usage_reservation = "usage_reservation"  # hold: negative
    refund = "refund"  # unused part of a reservation returned after settlement: positive
    reservation_release = "reservation_release"  # whole hold returned after failure/expiry: positive
    bonus = "bonus"
    promotional = "promotional"
    purchase = "purchase"
    admin_adjustment = "admin_adjustment"
    expiration = "expiration"


class CreditWallet(Base, TimestampMixin):
    __tablename__ = "credit_wallets"
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)


class CreditBucket(Base, TimestampMixin):
    """A pool of credits of one kind. There is deliberately NO balance column:
    balance is always SUM(credit_transactions.amount) for the bucket."""

    __tablename__ = "credit_buckets"
    wallet_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("credit_wallets.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String(20))
    source_ref: Mapped[str] = mapped_column(String(100), default="")
    initial_amount: Mapped[Decimal] = mapped_column(AMOUNT)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CreditTransaction(Base):
    """Append-only (enforced by a PostgreSQL trigger). Corrections are compensating rows."""

    __tablename__ = "credit_transactions"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    wallet_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("credit_wallets.id"), index=True)
    bucket_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("credit_buckets.id"), index=True)
    type: Mapped[str] = mapped_column(String(30))
    amount: Mapped[Decimal] = mapped_column(AMOUNT)  # signed
    reference_type: Mapped[str] = mapped_column(String(30), default="")
    reference_id: Mapped[str] = mapped_column(String(100), default="")
    idempotency_key: Mapped[str] = mapped_column(String(200), unique=True)
    description: Mapped[str] = mapped_column(String(300), default="")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    actor_id: Mapped[uuid.UUID | None] = mapped_column()
    reverses_transaction_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("credit_transactions.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class CreditReservation(Base, TimestampMixin):
    __tablename__ = "credit_reservations"
    wallet_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("credit_wallets.id"), index=True)
    reference_id: Mapped[str] = mapped_column(String(100), default="")  # e.g. ai_request id
    amount_reserved: Mapped[Decimal] = mapped_column(AMOUNT)
    amount_final: Mapped[Decimal | None] = mapped_column(AMOUNT)
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)  # active|settled|released
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    idempotency_key: Mapped[str] = mapped_column(String(200), unique=True)


class CreditReservationItem(Base):
    __tablename__ = "credit_reservation_items"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    reservation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("credit_reservations.id", ondelete="CASCADE"), index=True)
    bucket_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("credit_buckets.id"))
    amount: Mapped[Decimal] = mapped_column(AMOUNT)
    seq: Mapped[int] = mapped_column(default=0)  # consumption order


class CreditAllocation(Base, TimestampMixin):
    """Exactly-once guard: one allocation per (source_type, source_id), e.g. per paid invoice."""

    __tablename__ = "credit_allocations"
    __table_args__ = (UniqueConstraint("source_type", "source_id"),)
    source_type: Mapped[str] = mapped_column(String(30))
    source_id: Mapped[str] = mapped_column(String(100))
    bucket_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("credit_buckets.id"))
    amount: Mapped[Decimal] = mapped_column(AMOUNT)


class CreditSetting(Base, TimestampMixin):
    __tablename__ = "credit_settings"
    key: Mapped[str] = mapped_column(String(60), unique=True)
    value: Mapped[dict | list | int | str | None] = mapped_column(JSON)
