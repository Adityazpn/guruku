"""Orders, webhooks and fulfilment.
Security rules (docs/SPEC_03 §19): the amount is computed server-side; webhook signatures are verified; webhooks only
IDENTIFY the order — the decision uses the gateway's own API (fetch_status); fulfilment is exactly-once via
fulfilled_at; every webhook is stored; the browser's return from checkout never grants anything."""
import json
import secrets
import uuid
from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.db import utcnow
from app.core.email import send_email
from app.credits import service as credits
from app.credits.models import BucketType, TxType
from app.payments.gateways import GatewayError, get_gateway
from app.payments.models import Invoice, Payment, PaymentOrder, PaymentWebhook
from app.subscriptions import service as subs
from app.subscriptions.models import CreditPackage, Plan, PlanPrice

ORDER_TTL = timedelta(hours=24)


class PaymentError(Exception):
    def __init__(self, code: str, status: int = 400):
        super().__init__(code)
        self.code, self.status = code, status


def new_order_no() -> str:
    return f"ORD-{utcnow():%Y%m%d}-{secrets.token_hex(4).upper()}"


def create_order(db: Session, user, kind: str, item_id, idempotency_key: str, gateway_name: str | None = None, return_created: bool = False):
    existing = db.scalar(select(PaymentOrder).where(PaymentOrder.user_id == user.id, PaymentOrder.idempotency_key == idempotency_key))
    if existing:
        return (existing, False) if return_created else existing
    if kind == "subscription":
        price = db.get(PlanPrice, item_id)
        plan = db.get(Plan, price.plan_id) if price else None
        if not price or not price.active or not plan or not plan.active:
            raise PaymentError("plan_not_available", 404)
        amount, desc, meta = price.amount_idr, f"Langganan {plan.name} ({price.cycle})", {"plan": plan.code, "cycle": price.cycle}
    elif kind == "credit_package":
        pkg = db.get(CreditPackage, item_id)
        if not pkg or not pkg.active:
            raise PaymentError("package_not_available", 404)
        amount, desc, meta = pkg.price_idr, f"Paket kredit {pkg.name}", {"package": pkg.name}
    else:
        raise PaymentError("invalid_kind")
    if amount <= 0:
        raise PaymentError("invalid_amount")
    try:
        gw = get_gateway(gateway_name)
    except GatewayError:
        raise PaymentError("gateway_unavailable", 503) from None
    order = PaymentOrder(user_id=user.id, order_no=new_order_no(), kind=kind, item_id=item_id, amount_idr=amount, status="created",
                         gateway=gw.name, idempotency_key=idempotency_key, meta={**meta, "description": desc})
    db.add(order)
    try:
        db.flush()
    except IntegrityError:  # concurrent twin with the same key
        db.rollback()
        order = db.scalar(select(PaymentOrder).where(PaymentOrder.user_id == user.id, PaymentOrder.idempotency_key == idempotency_key))
        return (order, False) if return_created else order
    try:
        ref, url = gw.create_checkout(order, user.email, desc)
    except Exception:  # noqa: BLE001  network/API failure at the gateway: nothing was charged
        order.status = "failed"
        db.commit()
        raise PaymentError("gateway_unavailable", 503) from None
    order.gateway_ref, order.checkout_url, order.status, order.expires_at = ref, url, "pending", utcnow() + ORDER_TTL
    db.commit()
    return (order, True) if return_created else order


# ------------------------------------------------------------------ webhooks
def handle_webhook(db: Session, gateway_name: str, headers, body: bytes) -> tuple[int, dict]:
    try:
        gw = get_gateway(gateway_name)
    except GatewayError:
        return 503, {"status": "gateway_not_configured"}
    if not gw.verify_webhook(headers, body):
        db.add(PaymentWebhook(gateway=gw.name, event_id=f"invalid:{uuid.uuid4()}", signature_valid=False,
                              payload={"size": len(body)}, process_status="rejected:bad_signature"))
        db.commit()
        return 401, {"status": "invalid_signature"}
    try:
        ev = gw.parse_webhook(body)
        payload = json.loads(body)
    except Exception:  # noqa: BLE001
        return 400, {"status": "unparseable"}
    wh = db.scalar(select(PaymentWebhook).where(PaymentWebhook.gateway == gw.name, PaymentWebhook.event_id == ev.event_id))
    if wh and not wh.process_status.startswith("error:gateway"):
        return 200, {"status": "duplicate"}
    if not wh:
        wh = PaymentWebhook(gateway=gw.name, event_id=ev.event_id, signature_valid=True, payload=payload)
        db.add(wh)
        try:
            db.flush()
        except IntegrityError:  # same event delivered concurrently: the other request handles it
            db.rollback()
            return 200, {"status": "duplicate"}
    wh.process_status = process_order(db, gw, ev.order_no)
    db.commit()
    return (503, {"status": wh.process_status}) if wh.process_status == "error:gateway_fetch" else (200, {"status": wh.process_status})


def process_order(db: Session, gw, order_no: str) -> str:
    """Decide from the gateway's OWN record of the transaction, never from webhook content."""
    order = db.scalar(select(PaymentOrder).where(PaymentOrder.order_no == order_no).with_for_update())
    if order is None:
        return "ignored:unknown_order"
    if order.fulfilled_at is not None:
        return "ignored:already_fulfilled"
    try:
        truth = gw.fetch_status(order)
    except Exception:  # noqa: BLE001  fail closed; a non-2xx makes the gateway retry later
        return "error:gateway_fetch"
    if truth is None:
        return "ignored:not_found_at_gateway"
    if truth.order_no != order.order_no:
        return "error:order_mismatch"
    if truth.status == "paid":
        if truth.amount_idr != order.amount_idr:
            return "error:amount_mismatch"
        fulfil(db, order, truth)
        return "processed"
    if truth.status in ("failed", "expired") and order.status in ("created", "pending"):
        order.status = truth.status
        return "processed"
    return "ignored:pending"


def reconcile_order(db: Session, order_no: str) -> str:
    order = db.scalar(select(PaymentOrder).where(PaymentOrder.order_no == order_no))
    if not order:
        raise PaymentError("not_found", 404)
    result = process_order(db, get_gateway(order.gateway), order_no)
    db.commit()
    return result


# ------------------------------------------------------------------ fulfilment (exactly once)
def fulfil(db: Session, order: PaymentOrder, truth) -> None:
    now = utcnow()
    claimed = db.execute(update(PaymentOrder).where(PaymentOrder.id == order.id, PaymentOrder.fulfilled_at.is_(None))
                         .values(fulfilled_at=now, status="paid")).rowcount
    if claimed != 1:
        return
    db.refresh(order)
    from app.users.models import User

    user = db.get(User, order.user_id)
    db.add(Payment(order_id=order.id, gateway=order.gateway, gateway_txn_id=truth.txn_id, status="paid", amount_idr=order.amount_idr,
                   method=truth.method, paid_at=now))
    w = credits.get_or_create_wallet(db, order.user_id)
    if order.kind == "credit_package":
        pkg = db.get(CreditPackage, order.item_id)
        credits.grant(db, w, bucket_type=BucketType.purchased, amount=pkg.credits, source_type="package_order", source_id=order.order_no,
                      tx_type=TxType.purchase, expires_at=(now + timedelta(days=pkg.purchased_expiry_days)) if pkg.purchased_expiry_days else None,
                      description=f"Pembelian {pkg.name}")
        if pkg.bonus_credits and pkg.bonus_credits > 0:  # promo bonus lives in its own bucket, never mixed with purchased credits
            credits.grant(db, w, bucket_type=BucketType.bonus, amount=pkg.bonus_credits, source_type="package_bonus", source_id=order.order_no,
                          tx_type=TxType.bonus, expires_at=now + timedelta(days=pkg.bonus_expiry_days), description=f"Bonus {pkg.name}")
    else:
        price = db.get(PlanPrice, order.item_id)
        subs.activate(db, order.user_id, db.get(Plan, price.plan_id), price.cycle, now)
    db.add(Invoice(number=f"INV-{now:%Y%m}-{order.order_no.split('-')[-1]}", user_id=order.user_id, order_id=order.id,
                   description=order.meta.get("description", ""), amount_idr=order.amount_idr, issued_at=now))
    if user:
        send_email(user.email, "Pembayaran diterima", f"Terima kasih. Pembayaran {order.order_no} sebesar Rp{order.amount_idr:,} telah kami terima.".replace(",", "."))


def notify_renewal(user, order: PaymentOrder, ends) -> None:
    send_email(user.email, "Langganan Anda segera berakhir",
               f"Langganan Anda berakhir pada {ends:%d-%m-%Y}. Perpanjang di sini: {order.checkout_url}\nTautan berlaku 24 jam.")


def expire_stale_orders(db: Session, now) -> int:
    rows = list(db.scalars(select(PaymentOrder).where(PaymentOrder.status == "pending", PaymentOrder.expires_at <= now, PaymentOrder.fulfilled_at.is_(None))))
    for o in rows:
        o.status = "expired"
    return len(rows)


