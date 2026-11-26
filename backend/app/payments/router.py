import json
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db, utcnow
from app.core.deps import get_current_user
from app.core.rate_limit import rate_limit
from app.payments import service
from app.payments.gateways import Fake, GatewayEvent
from app.payments.models import Invoice, PaymentOrder
from app.subscriptions import service as subs
from app.subscriptions.models import CreditPackage, Plan, PlanPrice
from app.users.models import User

router = APIRouter(tags=["billing"])


class SubCheckoutIn(BaseModel):
    plan_code: str = Field(max_length=40)
    cycle: str = Field(pattern="^(monthly|annual)$")


class PackageCheckoutIn(BaseModel):
    package_id: uuid.UUID


def _idem(key: str | None) -> str:
    if not key or not (8 <= len(key) <= 100):
        raise HTTPException(400, "idempotency_key_required")
    return key


def _guard(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except service.PaymentError as e:
        raise HTTPException(e.status, e.code) from None


def _order_out(o: PaymentOrder) -> dict:
    return {"order_no": o.order_no, "kind": o.kind, "description": o.meta.get("description", ""), "amount_idr": o.amount_idr, "status": o.status,
            "checkout_url": o.checkout_url if o.status == "pending" else None, "paid": o.fulfilled_at is not None, "created_at": o.created_at}


# ---- catalogue (public) ----
@router.get("/plans")
def plans(db: Session = Depends(get_db)):
    out = []
    for p in db.scalars(select(Plan).where(Plan.active.is_(True)).order_by(Plan.sort)):
        prices = {x.cycle: x.amount_idr for x in db.scalars(select(PlanPrice).where(PlanPrice.plan_id == p.id, PlanPrice.active.is_(True)))}
        out.append({"code": p.code, "name": p.name, "description": p.description, "credits_monthly": str(p.credits_monthly), "features": p.features, "prices": prices})
    return out


@router.get("/credit-packages")
def packages(db: Session = Depends(get_db)):
    return [{"id": str(k.id), "name": k.name, "credits": str(k.credits), "bonus_credits": str(k.bonus_credits), "price_idr": k.price_idr,
             "purchased_expiry_days": k.purchased_expiry_days, "bonus_expiry_days": k.bonus_expiry_days}
            for k in db.scalars(select(CreditPackage).where(CreditPackage.active.is_(True)).order_by(CreditPackage.sort))]


# ---- checkout: the client sends WHAT to buy, never a price ----
@router.post("/checkout/subscription", status_code=201, dependencies=[Depends(rate_limit("checkout", 20))])
def checkout_subscription(body: SubCheckoutIn, idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
                          user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    got = subs.get_price(db, body.plan_code, body.cycle)
    if not got:
        raise HTTPException(404, "plan_not_available")
    return _order_out(_guard(service.create_order, db, user, "subscription", got[1].id, _idem(idempotency_key)))


@router.post("/checkout/credits", status_code=201, dependencies=[Depends(rate_limit("checkout", 20))])
def checkout_credits(body: PackageCheckoutIn, idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
                     user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _order_out(_guard(service.create_order, db, user, "credit_package", body.package_id, _idem(idempotency_key)))


# ---- history / status (read-only: polling this NEVER grants anything) ----
@router.get("/orders")
def orders(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return [_order_out(o) for o in db.scalars(select(PaymentOrder).where(PaymentOrder.user_id == user.id).order_by(PaymentOrder.created_at.desc()).limit(100))]


@router.get("/orders/{order_no}")
def order(order_no: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    o = db.scalar(select(PaymentOrder).where(PaymentOrder.order_no == order_no, PaymentOrder.user_id == user.id))
    if not o:
        raise HTTPException(404, "not_found")
    return _order_out(o)


@router.get("/invoices")
def invoices(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return [{"number": i.number, "description": i.description, "amount_idr": i.amount_idr, "status": i.status, "issued_at": i.issued_at}
            for i in db.scalars(select(Invoice).where(Invoice.user_id == user.id).order_by(Invoice.issued_at.desc()).limit(100))]


# ---- subscription ----
@router.get("/subscription")
def my_subscription(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    s = subs.live(db, user.id)
    if not s:
        return {"active": False}
    p = db.get(Plan, s.plan_id)
    return {"active": True, "plan_code": p.code, "plan_name": p.name, "cycle": s.cycle, "status": s.status, "period_end": s.period_end,
            "grace_until": s.grace_until, "cancel_at_period_end": s.cancel_at_period_end, "credits_monthly": str(p.credits_monthly)}


@router.post("/subscription/cancel", status_code=204)
def cancel(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    s = subs.live(db, user.id, lock=True)
    if not s:
        raise HTTPException(404, "no_subscription")
    s.cancel_at_period_end = True  # access continues until the paid period ends; no refund implied
    db.commit()


@router.post("/subscription/resume", status_code=204)
def resume(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    s = subs.live(db, user.id, lock=True)
    if not s:
        raise HTTPException(404, "no_subscription")
    s.cancel_at_period_end = False
    db.commit()


# ---- webhooks: unauthenticated by design; authenticity comes from the gateway signature ----
@router.post("/webhooks/{gateway}", dependencies=[Depends(rate_limit("webhook", 300))])
async def webhook(gateway: str, request: Request, db: Session = Depends(get_db)):
    body = await request.body()
    if len(body) > 100_000:
        raise HTTPException(413, "too_large")
    status, payload = service.handle_webhook(db, gateway, {k.lower(): v for k, v in request.headers.items()}, body)
    if status != 200:
        raise HTTPException(status, payload["status"])
    return payload


# ---- development-only helper: simulates "the customer paid at the gateway" (does not exist in production) ----
@router.post("/dev/fake-pay/{order_no}")
def dev_fake_pay(order_no: str, outcome: str = "paid", user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    s = get_settings()
    if s.app_env != "development" or s.payment_gateway != "fake":
        raise HTTPException(404, "not_found")
    o = db.scalar(select(PaymentOrder).where(PaymentOrder.order_no == order_no, PaymentOrder.user_id == user.id))
    if not o:
        raise HTTPException(404, "not_found")
    if outcome not in ("paid", "failed", "expired"):
        raise HTTPException(422, "invalid_outcome")
    Fake.STATUS[o.order_no] = GatewayEvent(f"{o.order_no}:{outcome}", o.order_no, outcome, o.amount_idr, f"fake-txn-{o.order_no}", "fake")
    body = json.dumps({"event_id": f"{o.order_no}:{outcome}:{utcnow().timestamp()}", "order_no": o.order_no, "status": outcome,
                       "amount_idr": o.amount_idr, "txn_id": f"fake-txn-{o.order_no}"}).encode()
    gw = Fake()
    status, payload = service.handle_webhook(db, "fake", {"x-fake-signature": gw.sign(body)}, body)
    return {"status": status, **payload}
