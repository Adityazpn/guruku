"""Credit ledger service.

Invariants (see docs/SPEC_03 §15-17):
  * balance(bucket) = SUM(ledger.amount); no editable counter exists.
  * every write that can reduce a balance first row-locks the wallet's buckets (ordered by id),
    so concurrent requests serialize and a bucket can never go negative.
  * every ledger row has a unique idempotency key; retries are harmless.
  * ledger rows are never updated or deleted; corrections are compensating rows.
"""
import uuid
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.db import utcnow
from app.credits.models import (
    BucketType,
    CreditAllocation,
    CreditBucket,
    CreditReservation,
    CreditReservationItem,
    CreditSetting,
    CreditTransaction,
    CreditWallet,
    TxType,
)

CENT = Decimal("0.01")
DEFAULT_PRIORITY = [BucketType.subscription.value, BucketType.bonus.value, BucketType.purchased.value]
DEFAULT_RESERVATION_TTL = timedelta(minutes=15)


class CreditError(Exception):
    code = "credit_error"


class InsufficientCredits(CreditError):
    code = "insufficient_credits"


class InvalidAmount(CreditError):
    code = "invalid_amount"


def dec(x) -> Decimal:
    return Decimal(str(x)).quantize(CENT)


def _aware(dt: datetime | None) -> datetime | None:
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=utcnow().tzinfo)
    return dt


# ---------- settings ----------
def get_setting(db: Session, key: str, default):
    row = db.scalar(select(CreditSetting).where(CreditSetting.key == key))
    return default if row is None or row.value is None else row.value


def consumption_priority(db: Session) -> list[str]:
    return list(get_setting(db, "consumption_priority", DEFAULT_PRIORITY))


# ---------- wallets & balances ----------
def get_or_create_wallet(db: Session, user_id: uuid.UUID) -> CreditWallet:
    w = db.scalar(select(CreditWallet).where(CreditWallet.user_id == user_id))
    if w:
        return w
    try:
        with db.begin_nested():
            w = CreditWallet(user_id=user_id)
            db.add(w)
            db.flush()
    except IntegrityError:  # concurrent creation
        w = db.scalar(select(CreditWallet).where(CreditWallet.user_id == user_id))
    return w


def bucket_balances(db: Session, wallet_id: uuid.UUID) -> dict[uuid.UUID, Decimal]:
    rows = db.execute(
        select(CreditTransaction.bucket_id, func.coalesce(func.sum(CreditTransaction.amount), 0))
        .where(CreditTransaction.wallet_id == wallet_id)
        .group_by(CreditTransaction.bucket_id)
    ).all()
    return {b: dec(s) for b, s in rows}


def summary(db: Session, wallet_id: uuid.UUID, now: datetime | None = None) -> dict:
    now = now or utcnow()
    bal = bucket_balances(db, wallet_id)
    out = {t.value: Decimal("0.00") for t in BucketType}
    soonest = None
    for b in db.scalars(select(CreditBucket).where(CreditBucket.wallet_id == wallet_id)):
        exp = _aware(b.expires_at)
        if exp is not None and exp <= now:
            continue
        amt = bal.get(b.id, Decimal("0.00"))
        if amt > 0:
            out[b.type] += amt
            if exp and (soonest is None or exp < soonest):
                soonest = exp
    out["total"] = sum(out.values(), Decimal("0.00"))
    out["next_expiry"] = soonest
    return out


# ---------- credit-adding operations ----------
def _tx(db, *, wallet_id, bucket_id, type_, amount, key, ref_type="", ref_id="", desc="", expires_at=None,
        actor_id=None, reverses=None) -> CreditTransaction:
    t = CreditTransaction(
        wallet_id=wallet_id, bucket_id=bucket_id, type=getattr(type_, "value", type_), amount=amount,
        reference_type=ref_type, reference_id=str(ref_id), idempotency_key=key, description=desc[:300],
        expires_at=expires_at, actor_id=actor_id, reverses_transaction_id=reverses,
    )
    db.add(t)
    return t


def grant(db: Session, wallet: CreditWallet, *, bucket_type: BucketType, amount, source_type: str, source_id: str,
          tx_type: TxType, expires_at: datetime | None = None, description: str = "",
          actor_id: uuid.UUID | None = None) -> CreditBucket:
    """Create a bucket with credits. Idempotent per (source_type, source_id): a repeated billing event
    returns the existing bucket and adds nothing."""
    amount = dec(amount)
    if amount <= 0:
        raise InvalidAmount("grant amount must be positive")
    existing = db.scalar(select(CreditAllocation).where(
        CreditAllocation.source_type == source_type, CreditAllocation.source_id == str(source_id)))
    if existing:
        return db.get(CreditBucket, existing.bucket_id)
    try:
        with db.begin_nested():
            bucket = CreditBucket(wallet_id=wallet.id, type=bucket_type.value, source_ref=f"{source_type}:{source_id}",
                                  initial_amount=amount, expires_at=expires_at)
            db.add(bucket)
            db.flush()
            # unique (source_type, source_id) makes the concurrent loser fail here, rolling back its bucket
            db.add(CreditAllocation(source_type=source_type, source_id=str(source_id), bucket_id=bucket.id, amount=amount))
            db.flush()
            _tx(db, wallet_id=wallet.id, bucket_id=bucket.id, type_=tx_type, amount=amount,
                key=f"alloc:{source_type}:{source_id}", ref_type=source_type, ref_id=source_id,
                desc=description, expires_at=expires_at, actor_id=actor_id)
            db.flush()
    except IntegrityError:
        existing = db.scalar(select(CreditAllocation).where(
            CreditAllocation.source_type == source_type, CreditAllocation.source_id == str(source_id)))
        if not existing:
            raise
        return db.get(CreditBucket, existing.bucket_id)
    return bucket


def grant_trial(db: Session, user_id: uuid.UUID) -> None:
    amount = get_setting(db, "trial_credits", 10)
    days = get_setting(db, "trial_days", 14)
    if not amount:
        return
    w = get_or_create_wallet(db, user_id)
    grant(db, w, bucket_type=BucketType.bonus, amount=amount, source_type="trial", source_id=str(user_id),
          tx_type=TxType.bonus, expires_at=utcnow() + timedelta(days=int(days)), description="Free trial credits")


# ---------- reservation ----------
def _lock_buckets(db: Session, wallet_id: uuid.UUID, only: set[uuid.UUID] | None = None) -> list[CreditBucket]:
    q = select(CreditBucket).where(CreditBucket.wallet_id == wallet_id)
    if only is not None:
        q = q.where(CreditBucket.id.in_(only))
    return list(db.scalars(q.order_by(CreditBucket.id).with_for_update()))  # canonical order => no deadlocks


def _consumption_order(buckets: list[CreditBucket], priority: list[str]) -> list[CreditBucket]:
    rank = {t: i for i, t in enumerate(priority)}
    far = datetime.max.replace(tzinfo=utcnow().tzinfo)
    return sorted(buckets, key=lambda b: (rank.get(b.type, len(rank)), _aware(b.expires_at) or far, _aware(b.created_at) or far))


def reserve(db: Session, wallet_id: uuid.UUID, amount, *, idempotency_key: str, reference_id: str = "",
            ttl: timedelta = DEFAULT_RESERVATION_TTL, now: datetime | None = None) -> CreditReservation:
    amount = dec(amount)
    if amount <= 0:
        raise InvalidAmount("reservation must be positive")
    now = now or utcnow()
    existing = db.scalar(select(CreditReservation).where(CreditReservation.idempotency_key == idempotency_key))
    if existing:
        return existing
    buckets = _lock_buckets(db, wallet_id)
    # re-check under lock: a concurrent twin may have committed while we waited
    existing = db.scalar(select(CreditReservation).where(CreditReservation.idempotency_key == idempotency_key))
    if existing:
        return existing
    balances = bucket_balances(db, wallet_id)
    usable = [b for b in buckets if (_aware(b.expires_at) is None or _aware(b.expires_at) > now)
              and balances.get(b.id, Decimal(0)) > 0]
    usable = _consumption_order(usable, consumption_priority(db))
    if sum((balances[b.id] for b in usable), Decimal(0)) < amount:
        raise InsufficientCredits(f"need {amount}")
    res = CreditReservation(wallet_id=wallet_id, reference_id=reference_id, amount_reserved=amount, status="active",
                            expires_at=now + ttl, idempotency_key=idempotency_key)
    db.add(res)
    db.flush()
    remaining = amount
    for seq, b in enumerate(usable):
        if remaining <= 0:
            break
        take = min(balances[b.id], remaining)
        db.add(CreditReservationItem(reservation_id=res.id, bucket_id=b.id, amount=take, seq=seq))
        _tx(db, wallet_id=wallet_id, bucket_id=b.id, type_=TxType.usage_reservation, amount=-take,
            key=f"resv:{res.id}:{b.id}", ref_type="reservation", ref_id=res.id, desc="Credit hold for AI request")
        remaining -= take
    db.flush()
    return res


def _items(db: Session, res_id: uuid.UUID) -> list[CreditReservationItem]:
    return list(db.scalars(select(CreditReservationItem).where(CreditReservationItem.reservation_id == res_id)
                           .order_by(CreditReservationItem.seq)))


def _lock_active(db: Session, reservation_id: uuid.UUID) -> CreditReservation | None:
    res = db.scalar(select(CreditReservation).where(CreditReservation.id == reservation_id)
                    .with_for_update().execution_options(populate_existing=True))
    return res if res and res.status == "active" else None


def settle(db: Session, reservation_id: uuid.UUID, final_amount) -> CreditReservation:
    """Charge `final_amount` (capped at the reserved amount); return the unused part to the buckets
    that were drawn last. Idempotent: a settled/released reservation is returned unchanged."""
    final = dec(final_amount)
    if final < 0:
        raise InvalidAmount("final amount must be >= 0")
    res = _lock_active(db, reservation_id)
    if res is None:
        return db.get(CreditReservation, reservation_id)
    items = _items(db, res.id)
    _lock_buckets(db, res.wallet_id, {i.bucket_id for i in items})
    final = min(final, res.amount_reserved)
    unused = res.amount_reserved - final
    for it in reversed(items):  # give back to the last-consumed buckets first
        if unused <= 0:
            break
        back = min(it.amount, unused)
        _tx(db, wallet_id=res.wallet_id, bucket_id=it.bucket_id, type_=TxType.refund, amount=back,
            key=f"settle:{res.id}:{it.bucket_id}", ref_type="reservation", ref_id=res.id,
            desc="Unused reserved credits returned")
        unused -= back
    res.status, res.amount_final = "settled", final
    db.flush()
    return res


def release(db: Session, reservation_id: uuid.UUID) -> CreditReservation:
    """Return the entire hold (AI request failed / reservation expired). Idempotent."""
    res = _lock_active(db, reservation_id)
    if res is None:
        return db.get(CreditReservation, reservation_id)
    items = _items(db, res.id)
    _lock_buckets(db, res.wallet_id, {i.bucket_id for i in items})
    for it in items:
        _tx(db, wallet_id=res.wallet_id, bucket_id=it.bucket_id, type_=TxType.reservation_release, amount=it.amount,
            key=f"release:{res.id}:{it.bucket_id}", ref_type="reservation", ref_id=res.id, desc="Credit hold released")
    res.status, res.amount_final = "released", Decimal("0.00")
    db.flush()
    return res


def sweep_expired_reservations(db: Session, now: datetime | None = None) -> int:
    now = now or utcnow()
    ids = list(db.scalars(select(CreditReservation.id).where(
        CreditReservation.status == "active", CreditReservation.expires_at <= now)))
    for rid in ids:
        release(db, rid)
    return len(ids)


# ---------- admin / maintenance ----------
def adjust(db: Session, bucket_id: uuid.UUID, amount, *, reason: str, actor_id: uuid.UUID, idempotency_key: str) -> CreditTransaction:
    """Auditable manual change. Never lets the bucket go below zero."""
    amount = dec(amount)
    if amount == 0 or not reason.strip():
        raise InvalidAmount("non-zero amount and a reason are required")
    bucket = db.get(CreditBucket, bucket_id)
    existing = db.scalar(select(CreditTransaction).where(CreditTransaction.idempotency_key == idempotency_key))
    if existing:
        return existing
    _lock_buckets(db, bucket.wallet_id, {bucket_id})
    if amount < 0 and bucket_balances(db, bucket.wallet_id).get(bucket_id, Decimal(0)) + amount < 0:
        raise InsufficientCredits("adjustment would make the balance negative")
    t = _tx(db, wallet_id=bucket.wallet_id, bucket_id=bucket_id, type_=TxType.admin_adjustment, amount=amount,
            key=idempotency_key, ref_type="admin", ref_id=str(actor_id), desc=reason, actor_id=actor_id)
    db.flush()
    return t


def compensate(db: Session, transaction_id: uuid.UUID, *, reason: str, actor_id: uuid.UUID) -> CreditTransaction:
    """Reverse a ledger row with an opposite row (history itself is never edited). Once per original."""
    orig = db.get(CreditTransaction, transaction_id)
    if orig is None:
        raise CreditError("unknown transaction")
    key = f"compensate:{orig.id}"
    existing = db.scalar(select(CreditTransaction).where(CreditTransaction.idempotency_key == key))
    if existing:
        return existing
    _lock_buckets(db, orig.wallet_id, {orig.bucket_id})
    if -orig.amount < 0 and bucket_balances(db, orig.wallet_id).get(orig.bucket_id, Decimal(0)) - orig.amount < 0:
        raise InsufficientCredits("reversal would make the balance negative")
    t = _tx(db, wallet_id=orig.wallet_id, bucket_id=orig.bucket_id, type_=TxType.admin_adjustment, amount=-orig.amount,
            key=key, ref_type="reversal", ref_id=orig.id, desc=reason, actor_id=actor_id, reverses=orig.id)
    db.flush()
    return t


def expire_buckets(db: Session, now: datetime | None = None) -> int:
    """Write `expiration` rows for the remaining balance of expired buckets (history untouched)."""
    now = now or utcnow()
    n = 0
    for b in list(db.scalars(select(CreditBucket).where(CreditBucket.expires_at.is_not(None), CreditBucket.expires_at <= now))):
        _lock_buckets(db, b.wallet_id, {b.id})
        bal = bucket_balances(db, b.wallet_id).get(b.id, Decimal(0))
        if bal > 0:
            prior = db.scalar(select(func.count()).select_from(CreditTransaction).where(
                CreditTransaction.bucket_id == b.id, CreditTransaction.type == TxType.expiration.value))
            _tx(db, wallet_id=b.wallet_id, bucket_id=b.id, type_=TxType.expiration, amount=-bal,
                key=f"expire:{b.id}:{prior}", ref_type="expiry", ref_id=b.id, desc="Credits expired")
            n += 1
    db.flush()
    return n
