"""Admin: plans, prices, credit packages, orders, webhook inspector, reconciliation. super_admin only; all writes audited."""
import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.admin.audit import audit
from app.core.db import get_db
from app.core.deps import require_roles
from app.payments import service
from app.payments.models import PaymentOrder, PaymentWebhook
from app.subscriptions.models import CreditPackage, Plan, PlanPrice
from app.users.models import User

router = APIRouter(prefix="/admin", tags=["admin-commerce"], dependencies=[Depends(require_roles("super_admin"))])
root = Depends(require_roles("super_admin"))


class PlanIn(BaseModel):
    code: str = Field(pattern="^[a-z][a-z0-9_-]{1,39}$")
    name: str = Field(min_length=2, max_length=100)
    description: str = Field(default="", max_length=500)
    credits_monthly: Decimal = Field(ge=0, le=100000)
    features: list[str] = Field(default_factory=list, max_length=20)
    monthly_price_idr: int | None = Field(default=None, ge=1000, le=100_000_000)
    annual_price_idr: int | None = Field(default=None, ge=1000, le=1_000_000_000)
    sort: int = 0


class PlanPatch(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    credits_monthly: Decimal | None = Field(default=None, ge=0, le=100000)
    features: list[str] | None = Field(default=None, max_length=20)
    active: bool | None = None
    monthly_price_idr: int | None = Field(default=None, ge=1000, le=100_000_000)
    annual_price_idr: int | None = Field(default=None, ge=1000, le=1_000_000_000)


class PackageIn(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    credits: Decimal = Field(gt=0, le=1_000_000)
    price_idr: int = Field(ge=1000, le=1_000_000_000)
    bonus_credits: Decimal = Field(default=Decimal(0), ge=0, le=1_000_000)
    bonus_expiry_days: int = Field(default=30, ge=1, le=3650)
    purchased_expiry_days: int | None = Field(default=None, ge=1, le=3650)
    sort: int = 0


class PackagePatch(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=100)
    price_idr: int | None = Field(default=None, ge=1000, le=1_000_000_000)
    credits: Decimal | None = Field(default=None, gt=0, le=1_000_000)
    bonus_credits: Decimal | None = Field(default=None, ge=0, le=1_000_000)
    active: bool | None = None


def _set_price(db: Session, plan: Plan, cycle: str, amount: int | None):
    if amount is None:
        return
    for old in db.scalars(select(PlanPrice).where(PlanPrice.plan_id == plan.id, PlanPrice.cycle == cycle, PlanPrice.active.is_(True))):
        old.active = False  # old price rows stay (history); existing orders keep the amount they were created with
    db.add(PlanPrice(plan_id=plan.id, cycle=cycle, amount_idr=amount))


def _plan_out(db: Session, p: Plan) -> dict:
    prices = {x.cycle: x.amount_idr for x in db.scalars(select(PlanPrice).where(PlanPrice.plan_id == p.id, PlanPrice.active.is_(True)))}
    return {"id": str(p.id), "code": p.code, "name": p.name, "description": p.description, "credits_monthly": str(p.credits_monthly),
            "features": p.features, "active": p.active, "prices": prices, "sort": p.sort}


def _pkg_out(k: CreditPackage) -> dict:
    return {"id": str(k.id), "name": k.name, "credits": str(k.credits), "price_idr": k.price_idr, "bonus_credits": str(k.bonus_credits), "active": k.active,
            "bonus_expiry_days": k.bonus_expiry_days, "purchased_expiry_days": k.purchased_expiry_days}


@router.get("/plans")
def list_plans(db: Session = Depends(get_db)):
    return [_plan_out(db, p) for p in db.scalars(select(Plan).order_by(Plan.sort))]


@router.post("/plans", status_code=201)
def create_plan(body: PlanIn, request: Request, user: User = root, db: Session = Depends(get_db)):
    if db.scalar(select(Plan).where(Plan.code == body.code)):
        raise HTTPException(409, "plan_exists")
    p = Plan(code=body.code, name=body.name, description=body.description, credits_monthly=body.credits_monthly, features=body.features, sort=body.sort)
    db.add(p)
    db.flush()
    _set_price(db, p, "monthly", body.monthly_price_idr)
    _set_price(db, p, "annual", body.annual_price_idr)
    db.flush()
    db.refresh(p)
    audit(db, user, "plan.create", "plan", p.id, after=body.model_dump(mode="json"), request=request)
    db.commit()
    return _plan_out(db, p)


@router.patch("/plans/{pid}")
def patch_plan(pid: uuid.UUID, body: PlanPatch, request: Request, user: User = root, db: Session = Depends(get_db)):
    p = db.get(Plan, pid)
    if not p:
        raise HTTPException(404, "not_found")
    before = _plan_out(db, p)
    ch = body.model_dump(exclude_none=True)
    for k in ("name", "description", "credits_monthly", "features", "active"):
        if k in ch:
            setattr(p, k, ch[k])
    _set_price(db, p, "monthly", ch.get("monthly_price_idr"))
    _set_price(db, p, "annual", ch.get("annual_price_idr"))
    db.flush()
    db.refresh(p)
    audit(db, user, "plan.update", "plan", p.id, before=before, after=_plan_out(db, p), request=request)
    db.commit()
    return _plan_out(db, p)


@router.get("/credit-packages")
def list_packages(db: Session = Depends(get_db)):
    return [_pkg_out(k) for k in db.scalars(select(CreditPackage).order_by(CreditPackage.sort))]


@router.post("/credit-packages", status_code=201)
def create_package(body: PackageIn, request: Request, user: User = root, db: Session = Depends(get_db)):
    k = CreditPackage(**body.model_dump())
    db.add(k)
    db.flush()
    db.refresh(k)
    audit(db, user, "package.create", "package", k.id, after=body.model_dump(mode="json"), request=request)
    db.commit()
    return _pkg_out(k)


@router.patch("/credit-packages/{kid}")
def patch_package(kid: uuid.UUID, body: PackagePatch, request: Request, user: User = root, db: Session = Depends(get_db)):
    k = db.get(CreditPackage, kid)
    if not k:
        raise HTTPException(404, "not_found")
    before = _pkg_out(k)
    for f, v in body.model_dump(exclude_none=True).items():
        setattr(k, f, v)
    db.flush()
    db.refresh(k)
    audit(db, user, "package.update", "package", k.id, before=before, after=_pkg_out(k), request=request)
    db.commit()
    return _pkg_out(k)


@router.get("/orders")
def admin_orders(status: str | None = None, page: int = Query(1, ge=1), db: Session = Depends(get_db)):
    q = select(PaymentOrder).order_by(PaymentOrder.created_at.desc())
    if status:
        q = q.where(PaymentOrder.status == status)
    return [{"order_no": o.order_no, "user_id": str(o.user_id), "kind": o.kind, "amount_idr": o.amount_idr, "status": o.status, "gateway": o.gateway,
             "fulfilled": o.fulfilled_at is not None, "created_at": o.created_at} for o in db.scalars(q.offset((page - 1) * 50).limit(50))]


@router.get("/webhooks")
def admin_webhooks(page: int = Query(1, ge=1), db: Session = Depends(get_db)):
    q = select(PaymentWebhook).order_by(PaymentWebhook.received_at.desc()).offset((page - 1) * 50).limit(50)
    return [{"id": str(w.id), "gateway": w.gateway, "event_id": w.event_id, "signature_valid": w.signature_valid, "status": w.process_status,
             "received_at": w.received_at, "payload": w.payload} for w in db.scalars(q)]


@router.post("/orders/{order_no}/reconcile")
def reconcile(order_no: str, request: Request, user: User = root, db: Session = Depends(get_db)):
    """Ask the gateway for the truth about this order and fulfil it if (and only if) it is paid and not yet fulfilled."""
    try:
        result = service.reconcile_order(db, order_no)
    except service.PaymentError as e:
        raise HTTPException(e.status, e.code) from None
    audit(db, user, "order.reconcile", "order", order_no, after={"result": result}, request=request)
    db.commit()
    return {"result": result}
