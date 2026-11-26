import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin, utcnow


class PaymentOrder(Base, TimestampMixin):
    __tablename__ = "payment_orders"
    __table_args__ = (UniqueConstraint("user_id", "idempotency_key"),)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    order_no: Mapped[str] = mapped_column(String(40), unique=True)
    kind: Mapped[str] = mapped_column(String(20))  # subscription | credit_package
    item_id: Mapped[uuid.UUID] = mapped_column()  # plan_prices.id or credit_packages.id
    amount_idr: Mapped[int] = mapped_column()  # computed by the SERVER from the catalogue, never from the client
    status: Mapped[str] = mapped_column(String(12), default="created", index=True)  # created|pending|paid|failed|expired
    gateway: Mapped[str] = mapped_column(String(20))
    gateway_ref: Mapped[str | None] = mapped_column(String(120))
    checkout_url: Mapped[str | None] = mapped_column(String(500))
    idempotency_key: Mapped[str] = mapped_column(String(120))
    fulfilled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # set exactly once => exactly-once fulfilment
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    meta: Mapped[dict] = mapped_column(JSON, default=dict)


class Payment(Base, TimestampMixin):
    __tablename__ = "payments"
    __table_args__ = (UniqueConstraint("gateway", "gateway_txn_id"),)
    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("payment_orders.id"), index=True)
    gateway: Mapped[str] = mapped_column(String(20))
    gateway_txn_id: Mapped[str | None] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(12))
    amount_idr: Mapped[int] = mapped_column()
    method: Mapped[str] = mapped_column(String(40), default="")
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PaymentWebhook(Base):
    """Every inbound webhook, valid or not. Headers are NOT stored (they carry the callback token)."""

    __tablename__ = "payment_webhooks"
    __table_args__ = (UniqueConstraint("gateway", "event_id"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    gateway: Mapped[str] = mapped_column(String(20))
    event_id: Mapped[str] = mapped_column(String(200))
    signature_valid: Mapped[bool] = mapped_column(Boolean)
    payload: Mapped[dict | None] = mapped_column(JSON)
    process_status: Mapped[str] = mapped_column(String(30), default="received")  # received|processed|ignored|error:<code>
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class Invoice(Base, TimestampMixin):
    __tablename__ = "invoices"
    number: Mapped[str] = mapped_column(String(40), unique=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("payment_orders.id"), unique=True)
    description: Mapped[str] = mapped_column(String(200))
    amount_idr: Mapped[int] = mapped_column()
    status: Mapped[str] = mapped_column(String(10), default="paid")
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
