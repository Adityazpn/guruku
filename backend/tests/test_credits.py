import threading
import uuid
from datetime import timedelta
from decimal import Decimal as D

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core.db import utcnow
from app.credits import service as cs
from app.credits.models import BucketType as BT
from app.credits.models import CreditTransaction, TxType
from app.users.models import User


def make_wallet(S):
    with S() as db:
        u = User(email=f"{uuid.uuid4()}@x.id", password_hash="x")
        db.add(u)
        db.flush()
        w = cs.get_or_create_wallet(db, u.id)
        db.commit()
        return u.id, w.id


def add(S, wid, bt, amt, key=None, days=None, tx=TxType.bonus):
    with S() as db:
        w = db.get(cs.CreditWallet, wid)
        b = cs.grant(db, w, bucket_type=bt, amount=amt, source_type="test", source_id=key or str(uuid.uuid4()),
                     tx_type=tx, expires_at=utcnow() + timedelta(days=days) if days else None)
        db.commit()
        return b.id


def summ(S, wid):
    with S() as db:
        return cs.summary(db, wid)


def test_grant_is_idempotent_per_billing_event(pg):
    _, wid = make_wallet(pg)
    a = add(pg, wid, BT.subscription, 100, key="invoice-1", tx=TxType.subscription_allocation)
    b = add(pg, wid, BT.subscription, 100, key="invoice-1", tx=TxType.subscription_allocation)
    assert a == b and summ(pg, wid)["total"] == D("100.00")


def test_spec_example_multi_bucket_reserve_and_settle(pg):
    _, wid = make_wallet(pg)
    add(pg, wid, BT.subscription, 4, tx=TxType.subscription_allocation, days=5)
    add(pg, wid, BT.bonus, 10, days=30)
    add(pg, wid, BT.purchased, 20, tx=TxType.purchase)
    with pg() as db:
        r = cs.reserve(db, wid, "7.5", idempotency_key="k1")
        db.commit()
        rid = r.id
    s = summ(pg, wid)
    assert (s["subscription"], s["bonus"], s["purchased"]) == (D("0"), D("6.50"), D("20"))
    with pg() as db:
        cs.settle(db, rid, "5.5")
        db.commit()
    s = summ(pg, wid)
    assert (s["subscription"], s["bonus"], s["purchased"]) == (D("0"), D("8.50"), D("20"))


def test_earliest_expiring_bonus_first_and_expired_unusable(pg):
    _, wid = make_wallet(pg)
    late = add(pg, wid, BT.bonus, 5, days=30)
    soon = add(pg, wid, BT.bonus, 5, days=3)
    with pg() as db:
        cs.reserve(db, wid, 4, idempotency_key="k")
        db.commit()
        bal = cs.bucket_balances(db, wid)
    assert bal[soon] == D("1.00") and bal[late] == D("5.00")
    # a bucket that already expired cannot be spent
    _, wid2 = make_wallet(pg)
    add(pg, wid2, BT.bonus, 5, days=-1)
    with pg() as db, pytest.raises(cs.InsufficientCredits):
        cs.reserve(db, wid2, 1, idempotency_key="k2")


def test_configurable_priority(pg):
    _, wid = make_wallet(pg)
    add(pg, wid, BT.subscription, 5, tx=TxType.subscription_allocation)
    p = add(pg, wid, BT.purchased, 5, tx=TxType.purchase)
    with pg() as db:
        db.add(cs.CreditSetting(key="consumption_priority", value=["purchased", "subscription", "bonus"]))
        db.commit()
        cs.reserve(db, wid, 3, idempotency_key="k")
        db.commit()
        assert cs.bucket_balances(db, wid)[p] == D("2.00")


def test_insufficient_writes_nothing(pg):
    _, wid = make_wallet(pg)
    add(pg, wid, BT.bonus, 2)
    with pg() as db:
        with pytest.raises(cs.InsufficientCredits):
            cs.reserve(db, wid, 3, idempotency_key="big")
        db.rollback()
        assert db.query(cs.CreditReservation).count() == 0
    assert summ(pg, wid)["total"] == D("2.00")


def test_reserve_idempotent_and_settle_release_once(pg):
    _, wid = make_wallet(pg)
    add(pg, wid, BT.bonus, 10)
    with pg() as db:
        a = cs.reserve(db, wid, 4, idempotency_key="same")
        b = cs.reserve(db, wid, 4, idempotency_key="same")
        db.commit()
        assert a.id == b.id
        rid = a.id
    assert summ(pg, wid)["total"] == D("6.00")
    with pg() as db:
        cs.settle(db, rid, 1)
        cs.settle(db, rid, 1)  # duplicate
        cs.release(db, rid)  # late failure handler must not refund again
        db.commit()
    assert summ(pg, wid)["total"] == D("9.00")


def test_settle_is_capped_at_reserved_and_release_restores(pg):
    _, wid = make_wallet(pg)
    add(pg, wid, BT.bonus, 10)
    with pg() as db:
        r = cs.reserve(db, wid, 3, idempotency_key="a")
        cs.settle(db, r.id, 99)
        r2 = cs.reserve(db, wid, 3, idempotency_key="b")
        cs.release(db, r2.id)
        db.commit()
    assert summ(pg, wid)["total"] == D("7.00")


def test_sweeper_releases_stale_reservations(pg):
    _, wid = make_wallet(pg)
    add(pg, wid, BT.bonus, 10)
    with pg() as db:
        cs.reserve(db, wid, 4, idempotency_key="old", ttl=timedelta(minutes=1))
        db.commit()
        assert cs.sweep_expired_reservations(db, utcnow() + timedelta(minutes=5)) == 1
        db.commit()
    assert summ(pg, wid)["total"] == D("10.00")


def test_ledger_is_append_only(pg):
    _, wid = make_wallet(pg)
    add(pg, wid, BT.bonus, 10)
    for stmt in ("UPDATE credit_transactions SET amount = 999", "DELETE FROM credit_transactions"):
        with pg() as db, pytest.raises(DBAPIError, match="append-only"):
            db.execute(text(stmt))


def test_db_refuses_overdraft_even_if_service_bypassed(pg):
    _, wid = make_wallet(pg)
    bid = add(pg, wid, BT.bonus, 5)
    with pg() as db, pytest.raises(DBAPIError, match="negative"):
        db.add(CreditTransaction(wallet_id=wid, bucket_id=bid, type="admin_adjustment", amount=D("-6"),
                                 idempotency_key="raw"))
        db.flush()


def test_adjust_and_compensate(pg):
    _, wid = make_wallet(pg)
    bid = add(pg, wid, BT.bonus, 10)
    admin = uuid.uuid4()
    with pg() as db:
        with pytest.raises(cs.InsufficientCredits):
            cs.adjust(db, bid, -11, reason="oops", actor_id=admin, idempotency_key="adj0")
        with pytest.raises(cs.InvalidAmount):
            cs.adjust(db, bid, 1, reason=" ", actor_id=admin, idempotency_key="adj1")
        t = cs.adjust(db, bid, -4, reason="fraud correction", actor_id=admin, idempotency_key="adj2")
        db.commit()
        tid = t.id
    assert summ(pg, wid)["total"] == D("6.00")
    with pg() as db:
        cs.compensate(db, tid, reason="mistake", actor_id=admin)
        cs.compensate(db, tid, reason="mistake", actor_id=admin)  # once only
        db.commit()
    assert summ(pg, wid)["total"] == D("10.00")


def test_expire_buckets_writes_compensating_row_not_edits(pg):
    _, wid = make_wallet(pg)
    add(pg, wid, BT.bonus, 10, days=1)
    with pg() as db:
        assert cs.expire_buckets(db, utcnow() + timedelta(days=2)) == 1
        assert cs.expire_buckets(db, utcnow() + timedelta(days=2)) == 0
        db.commit()
        types = sorted(t.type for t in db.query(CreditTransaction))
    assert types == ["bonus", "expiration"]
    assert summ(pg, wid)["total"] == D("0.00")


# ---------------- concurrency ----------------
def run_threads(n, fn):
    barrier = threading.Barrier(n)
    results = [None] * n

    def worker(i):
        barrier.wait()
        try:
            results[i] = fn(i)
        except Exception as e:  # noqa: BLE001
            results[i] = e

    ts = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    return results


def test_concurrent_reservations_never_overspend(pg):
    _, wid = make_wallet(pg)
    add(pg, wid, BT.subscription, 10, tx=TxType.subscription_allocation)
    add(pg, wid, BT.bonus, 5)

    def go(i):
        with pg() as db:
            cs.reserve(db, wid, 1, idempotency_key=f"c{i}")
            db.commit()
            return "ok"

    res = run_threads(40, go)
    ok = [r for r in res if r == "ok"]
    bad = [r for r in res if isinstance(r, cs.InsufficientCredits)]
    assert len(ok) == 15 and len(bad) == 25, [r for r in res if r != "ok" and not isinstance(r, cs.InsufficientCredits)]
    with pg() as db:
        assert all(v >= 0 for v in cs.bucket_balances(db, wid).values())
    assert summ(pg, wid)["total"] == D("0.00")


def test_concurrent_same_idempotency_key_creates_one_hold(pg):
    _, wid = make_wallet(pg)
    add(pg, wid, BT.bonus, 10)

    def go(i):
        with pg() as db:
            r = cs.reserve(db, wid, 3, idempotency_key="dup")
            db.commit()
            return r.id

    ids = run_threads(12, go)
    assert all(isinstance(i, uuid.UUID) for i in ids), ids
    assert len(set(ids)) == 1
    assert summ(pg, wid)["total"] == D("7.00")


def test_concurrent_double_settle_refunds_once(pg):
    _, wid = make_wallet(pg)
    add(pg, wid, BT.bonus, 10)
    with pg() as db:
        rid = cs.reserve(db, wid, 6, idempotency_key="s").id
        db.commit()

    def go(i):
        with pg() as db:
            (cs.settle if i % 2 else lambda d, r, _x: cs.release(d, r))(db, rid, 2)
            db.commit()
            return "ok"

    res = run_threads(10, go)
    assert res == ["ok"] * 10, res
    # whichever finished first wins (settle=8 left, release=10 left) - but never both
    assert summ(pg, wid)["total"] in (D("8.00"), D("10.00"))
    with pg() as db:
        refunds = db.query(CreditTransaction).filter(CreditTransaction.type.in_(["refund", "reservation_release"])).count()
        assert refunds == 1


def test_concurrent_duplicate_grant_single_allocation(pg):
    _, wid = make_wallet(pg)

    def go(i):
        with pg() as db:
            w = db.get(cs.CreditWallet, wid)
            b = cs.grant(db, w, bucket_type=BT.subscription, amount=100, source_type="invoice", source_id="INV-1",
                         tx_type=TxType.subscription_allocation)
            db.commit()
            return b.id

    ids = run_threads(10, go)
    assert all(isinstance(i, uuid.UUID) for i in ids), ids
    assert summ(pg, wid)["total"] == D("100.00")
