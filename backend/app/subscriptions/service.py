"""Subscription lifecycle. State changes come ONLY from verified payments (payments.service.fulfil) or from the scheduled tick.

Credits: one allocation per elapsed month of the subscription span (annual plans therefore 'drip' monthly), each idempotent via
credit_allocations(source_type, source_id) and each expiring at the end of its month. No rollover.
Plan change = immediate switch with NO proration (the old plan's remaining paid time is not refunded or carried) -- a product decision to confirm."""
from calendar import monthrange
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import utcnow
from app.credits import service as credits
from app.credits.models import BucketType, TxType
from app.subscriptions.models import Plan, PlanPrice, Subscription

CYCLE_MONTHS = {"monthly": 1, "annual": 12}


def add_months(dt: datetime, n: int) -> datetime:
    y, m = dt.year + (dt.month - 1 + n) // 12, (dt.month - 1 + n) % 12 + 1
    return dt.replace(year=y, month=m, day=min(dt.day, monthrange(y, m)[1]))


def _aware(dt):
    return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=utcnow().tzinfo)


def live(db: Session, user_id, lock: bool = False) -> Subscription | None:
    q = select(Subscription).where(Subscription.user_id == user_id, Subscription.status.in_(("active", "past_due")))
    return db.scalar(q.with_for_update() if lock else q)


def get_price(db: Session, plan_code: str, cycle: str) -> tuple[Plan, PlanPrice] | None:
    row = db.execute(select(Plan, PlanPrice).join(PlanPrice, PlanPrice.plan_id == Plan.id).where(
        Plan.code == plan_code, Plan.active.is_(True), PlanPrice.cycle == cycle, PlanPrice.active.is_(True))).first()
    return (row[0], row[1]) if row else None


def allocate_credits(db: Session, sub: Subscription, now: datetime | None = None) -> int:
    now = now or utcnow()
    plan = db.get(Plan, sub.plan_id)
    start, end, n = _aware(sub.period_start), _aware(sub.period_end), 0
    if not plan or plan.credits_monthly <= 0:
        return 0
    for k in range(sub.months_paid):
        slice_start = add_months(start, k)
        if slice_start > now or slice_start >= end:
            break
        w = credits.get_or_create_wallet(db, sub.user_id)
        before = db.scalar(select(credits.CreditAllocation.id).where(
            credits.CreditAllocation.source_type == "subscription_slice", credits.CreditAllocation.source_id == f"{sub.id}:{k}"))
        credits.grant(db, w, bucket_type=BucketType.subscription, amount=plan.credits_monthly, source_type="subscription_slice",
                      source_id=f"{sub.id}:{k}", tx_type=TxType.subscription_allocation, expires_at=min(add_months(start, k + 1), end),
                      description=f"Kredit langganan {plan.name}")
        n += 0 if before else 1
    return n


def activate(db: Session, user_id, plan: Plan, cycle: str, now: datetime | None = None) -> Subscription:
    """Called by fulfilment of a verified payment. Extends the same plan, or switches plans immediately."""
    now = now or utcnow()
    months = CYCLE_MONTHS[cycle]
    cur = live(db, user_id, lock=True)
    if cur and cur.plan_id == plan.id and _aware(cur.period_end) > now:
        cur.months_paid += months  # early/on-time renewal: extend the same span
        cur.period_end = add_months(_aware(cur.period_start), cur.months_paid)
        cur.cycle, cur.status, cur.grace_until, cur.cancel_at_period_end = cycle, "active", None, False
        sub = cur
    else:
        if cur:  # lapsed (past_due) or different plan: close it before opening a new span
            cur.status = "expired"
            db.flush()
        sub = Subscription(user_id=user_id, plan_id=plan.id, cycle=cycle, status="active", period_start=now, months_paid=months,
                           period_end=add_months(now, months))
        db.add(sub)
    db.flush()
    allocate_credits(db, sub, now)
    return sub


def tick(db: Session, now: datetime | None = None) -> dict:
    """Scheduled housekeeping (every 15 min). Idempotent."""
    from app.payments import service as pay
    from app.users.models import User

    s, now = get_settings(), now or utcnow()
    out = {"allocated": 0, "renewal_orders": 0, "past_due": 0, "canceled": 0, "expired": 0, "orders_expired": 0}
    for sub in list(db.scalars(select(Subscription).where(Subscription.status.in_(("active", "past_due"))))):
        out["allocated"] += allocate_credits(db, sub, now)
        end = _aware(sub.period_end)
        if sub.status == "active" and not sub.cancel_at_period_end and now < end <= now + timedelta(days=s.renewal_notice_days):
            got = get_price(db, db.get(Plan, sub.plan_id).code, sub.cycle)
            user = db.get(User, sub.user_id)
            if got and user:
                order, created = pay.create_order(db, user, "subscription", got[1].id, f"renew:{sub.id}:{sub.months_paid}", return_created=True)
                if created:
                    out["renewal_orders"] += 1
                    pay.notify_renewal(user, order, end)
        if sub.status == "active" and end <= now:
            if sub.cancel_at_period_end:
                sub.status = "canceled"
                out["canceled"] += 1
            else:
                sub.status, sub.grace_until = "past_due", end + timedelta(days=s.grace_days)
                out["past_due"] += 1
        if sub.status == "past_due" and _aware(sub.grace_until) <= now:
            sub.status = "expired"
            out["expired"] += 1
    out["orders_expired"] = pay.expire_stale_orders(db, now)
    db.commit()
    return out
