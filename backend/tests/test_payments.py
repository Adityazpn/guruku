import base64
import hashlib
import json
from datetime import timedelta
from decimal import Decimal as D

import httpx
import pytest
from sqlalchemy import func, select

from app.core import config
from app.core import email as mailer
from app.core.db import utcnow
from app.credits import service as cs
from app.credits.models import CreditTransaction
from app.payments import service as pay
from app.payments.gateways import Fake, GatewayError, GatewayEvent, Midtrans, Xendit, get_gateway
from app.payments.models import Invoice, Payment, PaymentOrder, PaymentWebhook
from app.subscriptions import service as subs
from app.subscriptions.models import CreditPackage, Plan, PlanPrice, Subscription
from app.users.models import User
from tests.test_admin import login

A = "/api/v1"


@pytest.fixture(autouse=True)
def _reset():
    Fake.STATUS.clear()
    yield
    Fake.STATUS.clear()


@pytest.fixture
def shop(pg_client, pg):
    with pg() as db:
        starter = Plan(code="starter", name="Starter", credits_monthly=D("100"), sort=1)
        pro = Plan(code="pro", name="Professional", credits_monthly=D("300"), sort=2)
        db.add_all([starter, pro])
        db.flush()
        db.add_all([PlanPrice(plan_id=starter.id, cycle="monthly", amount_idr=49000), PlanPrice(plan_id=starter.id, cycle="annual", amount_idr=490000),
                    PlanPrice(plan_id=pro.id, cycle="monthly", amount_idr=99000)])
        db.add_all([CreditPackage(name="100 Kredit", credits=D("100"), price_idr=35000, bonus_credits=D("10"), bonus_expiry_days=30, purchased_expiry_days=365),
                    CreditPackage(name="Mati", credits=D("5"), price_idr=5000, active=False)])
        db.commit()
    c = pg_client
    return c, pg, login(c, pg, "buyer@x.id"), login(c, pg, "other@x.id")


def hook(c, order_no, status="paid", amount=None, event_id=None, sign=True, txn=None):
    body = json.dumps({"event_id": event_id or f"{order_no}:{status}", "order_no": order_no, "status": status, "amount_idr": amount or 0, "txn_id": txn or f"txn-{order_no}"}).encode()
    sig = Fake().sign(body) if sign else "deadbeef"
    return c.post(f"{A}/webhooks/fake", content=body, headers={"x-fake-signature": sig, "content-type": "application/json"})


def gateway_says(order_no, status, amount):
    Fake.STATUS[order_no] = GatewayEvent(f"{order_no}:{status}", order_no, status, amount, f"txn-{order_no}", "fake")


def buy_package(c, h, key="pkg-buy-0001"):
    pkg = next(p for p in c.get(f"{A}/credit-packages").json())
    r = c.post(f"{A}/checkout/credits", json={"package_id": pkg["id"]}, headers={**h, "Idempotency-Key": key})
    assert r.status_code == 201, r.text
    return r.json()


def buy_plan(c, h, code="starter", cycle="monthly", key="plan-buy-0001"):
    r = c.post(f"{A}/checkout/subscription", json={"plan_code": code, "cycle": cycle}, headers={**h, "Idempotency-Key": key})
    assert r.status_code == 201, r.text
    return r.json()


def pay_order(c, o):
    gateway_says(o["order_no"], "paid", o["amount_idr"])
    r = hook(c, o["order_no"], event_id=f"{o['order_no']}:paid:{utcnow().timestamp()}")
    assert r.status_code == 200, r.text
    return r.json()


def total(c, h):
    return D(c.get(f"{A}/credits/summary", headers=h).json()["total"])


# ---------------------------------------------------------------- checkout
def test_catalogue_is_public_and_checkout_requires_login(shop):
    c, pg, h, _ = shop
    plans = c.get(f"{A}/plans").json()
    assert [p["code"] for p in plans] == ["starter", "pro"] and plans[0]["prices"] == {"monthly": 49000, "annual": 490000}
    assert [k["name"] for k in c.get(f"{A}/credit-packages").json()] == ["100 Kredit"]  # inactive package hidden
    assert c.post(f"{A}/checkout/credits", json={"package_id": "00000000-0000-0000-0000-000000000000"}).status_code == 401


def test_price_comes_from_the_server_and_checkout_is_idempotent(shop):
    c, pg, h, _ = shop
    o = c.post(f"{A}/checkout/subscription", json={"plan_code": "starter", "cycle": "monthly", "amount_idr": 1}, headers={**h, "Idempotency-Key": "price-test-01"}).json()
    assert o["amount_idr"] == 49000 and o["status"] == "pending" and o["checkout_url"]  # client-sent amount ignored
    again = c.post(f"{A}/checkout/subscription", json={"plan_code": "starter", "cycle": "monthly"}, headers={**h, "Idempotency-Key": "price-test-01"}).json()
    assert again["order_no"] == o["order_no"]
    with pg() as db:
        assert db.scalar(select(func.count()).select_from(PaymentOrder)) == 1
    assert c.post(f"{A}/checkout/subscription", json={"plan_code": "starter", "cycle": "monthly"}, headers=h).status_code == 400  # key required
    assert c.post(f"{A}/checkout/subscription", json={"plan_code": "nope", "cycle": "monthly"}, headers={**h, "Idempotency-Key": "k-nope-0001"}).status_code == 404
    assert c.post(f"{A}/checkout/subscription", json={"plan_code": "starter", "cycle": "weekly"}, headers={**h, "Idempotency-Key": "k-weekly-01"}).status_code == 422
    bad = c.post(f"{A}/checkout/credits", json={"package_id": "00000000-0000-0000-0000-000000000000"}, headers={**h, "Idempotency-Key": "k-pkg-0001"})
    assert bad.status_code == 404
    with pg() as db:
        inactive = db.scalar(select(CreditPackage).where(CreditPackage.active.is_(False))).id
    assert c.post(f"{A}/checkout/credits", json={"package_id": str(inactive)}, headers={**h, "Idempotency-Key": "k-pkg-0002"}).status_code == 404


def test_returning_from_checkout_grants_nothing(shop):
    c, pg, h, _ = shop
    o = buy_package(c, h)
    before = total(c, h)
    for _ in range(3):  # the browser lands on the status page and polls; nothing may change
        st = c.get(f"{A}/orders/{o['order_no']}", headers=h).json()
        assert st["status"] == "pending" and st["paid"] is False
    assert total(c, h) == before
    buy_plan(c, h)
    assert c.get(f"{A}/subscription", headers=h).json() == {"active": False}


# ---------------------------------------------------------------- webhook security
def test_bad_signature_is_rejected_logged_and_changes_nothing(shop):
    c, pg, h, _ = shop
    o = buy_package(c, h)
    gateway_says(o["order_no"], "paid", o["amount_idr"])
    assert hook(c, o["order_no"], sign=False).status_code == 401
    assert c.post(f"{A}/webhooks/fake", content=b"{}", headers={}).status_code == 401
    assert total(c, h) == D("10.00")  # trial credits only
    with pg() as db:
        assert db.query(PaymentOrder).one().fulfilled_at is None
        assert db.query(PaymentWebhook).filter_by(signature_valid=False).count() == 2


def test_forged_paid_claim_is_ignored_when_the_gateway_says_pending(shop):
    """Even a correctly signed body is only a hint: the gateway's own API decides."""
    c, pg, h, _ = shop
    o = buy_package(c, h)
    gateway_says(o["order_no"], "pending", o["amount_idr"])
    r = hook(c, o["order_no"], status="paid", amount=o["amount_idr"])
    assert r.status_code == 200 and r.json()["status"] == "ignored:pending"
    assert total(c, h) == D("10.00")


def test_amount_mismatch_is_not_fulfilled(shop):
    c, pg, h, _ = shop
    o = buy_package(c, h)
    gateway_says(o["order_no"], "paid", 1000)  # paid far less than the price
    assert hook(c, o["order_no"]).json()["status"] == "error:amount_mismatch"
    assert total(c, h) == D("10.00")
    with pg() as db:
        assert db.query(PaymentOrder).one().fulfilled_at is None


def test_unknown_order_and_gateway_outage_fail_safely(shop, monkeypatch):
    c, pg, h, _ = shop
    assert hook(c, "ORD-UNKNOWN-1").json()["status"] == "ignored:unknown_order"
    o = buy_package(c, h)
    monkeypatch.setattr(Fake, "fetch_status", lambda self, order: (_ for _ in ()).throw(RuntimeError("gateway down")))
    r = hook(c, o["order_no"], event_id="evt-retry-1")
    assert r.status_code == 503 and total(c, h) == D("10.00")  # fail closed: gateway will retry
    monkeypatch.undo()
    gateway_says(o["order_no"], "paid", o["amount_idr"])
    assert hook(c, o["order_no"], event_id="evt-retry-1").json()["status"] == "processed"  # the retry (same event id) is processed
    assert total(c, h) == D("10.00") + D("110.00")


# ---------------------------------------------------------------- exactly-once fulfilment
def test_credit_package_gives_separate_purchased_and_bonus_buckets_once(shop):
    c, pg, h, _ = shop
    o = buy_package(c, h)
    assert pay_order(c, o)["status"] == "processed"
    s = c.get(f"{A}/credits/summary", headers=h).json()
    assert (D(s["purchased"]), D(s["bonus"])) == (D("100"), D("20"))  # 100 bought; 10 trial + 10 promo bonus
    with pg() as db:
        buyer = db.scalar(select(User).where(User.email == "buyer@x.id")).id
        w = cs.get_or_create_wallet(db, buyer).id
        types = sorted(t.type for t in db.query(CreditTransaction).filter_by(wallet_id=w))
        assert types == ["bonus", "bonus", "purchase"]  # trial + promo bonus (separate buckets) + the purchase
        assert db.query(Invoice).one().amount_idr == 35000 and db.query(Payment).one().amount_idr == 35000
        assert db.query(PaymentOrder).one().status == "paid"
    inv = c.get(f"{A}/invoices", headers=h).json()
    assert len(inv) == 1 and inv[0]["number"].startswith("INV-") and c.get(f"{A}/orders/{o['order_no']}", headers=h).json()["paid"] is True
    assert any("Pembayaran diterima" in m.subject for m in mailer.outbox)


def test_duplicate_and_replayed_webhooks_do_not_double_credit(shop):
    c, pg, h, _ = shop
    o = buy_package(c, h)
    gateway_says(o["order_no"], "paid", o["amount_idr"])
    assert hook(c, o["order_no"], event_id="e1").json()["status"] == "processed"
    assert hook(c, o["order_no"], event_id="e1").json()["status"] == "duplicate"  # same event redelivered
    assert hook(c, o["order_no"], event_id="e2").json()["status"] == "ignored:already_fulfilled"  # attacker/gateway replays with a new id
    assert total(c, h) == D("120.00")
    with pg() as db:
        assert db.query(Invoice).count() == 1 and db.query(CreditTransaction).filter(CreditTransaction.type == "purchase").count() == 1


def test_concurrent_webhook_deliveries_fulfil_exactly_once(shop):
    import threading

    c, pg, h, _ = shop
    o = buy_package(c, h)
    gateway_says(o["order_no"], "paid", o["amount_idr"])
    gw = Fake()
    results, barrier = [None] * 10, threading.Barrier(10)

    def go(i):
        body = json.dumps({"event_id": f"conc-{i % 3}", "order_no": o["order_no"], "status": "paid", "amount_idr": o["amount_idr"], "txn_id": "t"}).encode()
        barrier.wait()
        try:
            with pg() as db:
                results[i] = pay.handle_webhook(db, "fake", {"x-fake-signature": gw.sign(body)}, body)[1]["status"]
        except Exception as e:  # noqa: BLE001
            results[i] = repr(e)

    ts = [threading.Thread(target=go, args=(i,)) for i in range(10)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert results.count("processed") == 1, results
    assert total(c, h) == D("120.00")
    with pg() as db:
        assert db.query(Invoice).count() == 1 and db.query(Payment).count() == 1


def test_failed_or_expired_payment_never_activates(shop):
    c, pg, h, _ = shop
    o = buy_plan(c, h)
    gateway_says(o["order_no"], "failed", o["amount_idr"])
    assert hook(c, o["order_no"], status="failed").json()["status"] == "processed"
    assert c.get(f"{A}/orders/{o['order_no']}", headers=h).json()["status"] == "failed"
    assert c.get(f"{A}/subscription", headers=h).json() == {"active": False} and total(c, h) == D("10.00")


# ---------------------------------------------------------------- subscriptions
def test_paid_subscription_activates_and_allocates_expiring_credits(shop):
    c, pg, h, _ = shop
    pay_order(c, buy_plan(c, h))
    sub = c.get(f"{A}/subscription", headers=h).json()
    assert sub["active"] and sub["plan_code"] == "starter" and sub["status"] == "active"
    s = c.get(f"{A}/credits/summary", headers=h).json()
    assert D(s["subscription"]) == D("100.00")
    with pg() as db:
        b = db.query(subs.credits.CreditBucket).filter_by(type="subscription").one()
        sb = db.query(Subscription).one()
        assert b.expires_at.replace(tzinfo=None) == sb.period_end.replace(tzinfo=None)


def test_early_renewal_extends_span_and_credits_arrive_month_by_month(shop):
    c, pg, h, _ = shop
    pay_order(c, buy_plan(c, h, key="renew-key-01"))
    pay_order(c, buy_plan(c, h, key="renew-key-02"))  # paid again before the period ended
    with pg() as db:
        sb = db.query(Subscription).one()
        assert sb.months_paid == 2 and subs.add_months(sb.period_start, 2) == sb.period_end
    assert D(c.get(f"{A}/credits/summary", headers=h).json()["subscription"]) == D("100")  # second month's credits are not given early
    with pg() as db:
        assert subs.tick(db, now=utcnow() + timedelta(days=32))["allocated"] == 1
        assert subs.tick(db, now=utcnow() + timedelta(days=32))["allocated"] == 0  # idempotent


def test_annual_plan_drips_monthly_and_totals_twelve_months(shop):
    c, pg, h, _ = shop
    pay_order(c, buy_plan(c, h, cycle="annual"))
    with pg() as db:
        sb = db.query(Subscription).one()
        start = sb.period_start.replace(tzinfo=utcnow().tzinfo) if sb.period_start.tzinfo is None else sb.period_start
        got = 0
        for m in range(1, 14):
            got += subs.tick(db, now=subs.add_months(start, m) + timedelta(hours=1))["allocated"]
        assert got == 11  # month 0 was given at purchase; months 1..11 dripped; nothing after the span
        total_alloc = db.scalar(select(func.sum(CreditTransaction.amount)).where(CreditTransaction.type == "subscription_allocation"))
        assert total_alloc == D("1200.00")


def test_plan_change_switches_immediately_with_a_single_live_subscription(shop):
    c, pg, h, _ = shop
    pay_order(c, buy_plan(c, h, "starter", key="chg-key-0001"))
    pay_order(c, buy_plan(c, h, "pro", key="chg-key-0002"))
    assert c.get(f"{A}/subscription", headers=h).json()["plan_code"] == "pro"
    with pg() as db:
        assert sorted(s.status for s in db.query(Subscription)) == ["active", "expired"]


def test_lifecycle_past_due_grace_expiry_and_cancel(shop):
    c, pg, h, _ = shop
    pay_order(c, buy_plan(c, h))
    with pg() as db:
        sb = db.query(Subscription).one()
        end = sb.period_end if sb.period_end.tzinfo else sb.period_end.replace(tzinfo=utcnow().tzinfo)
        assert subs.tick(db, now=end + timedelta(hours=1))["past_due"] == 1
        assert db.query(Subscription).one().status == "past_due"
    assert c.get(f"{A}/subscription", headers=h).json()["status"] == "past_due"  # still visible during grace
    with pg() as db:
        assert subs.tick(db, now=end + timedelta(days=config.get_settings().grace_days, hours=1))["expired"] == 1
    assert c.get(f"{A}/subscription", headers=h).json() == {"active": False}
    # cancel at period end: access until the end, then canceled (never past_due)
    h2 = login(c, pg, "cancel@x.id")
    pay_order(c, buy_plan(c, h2, key="cancel-k-0001"))
    assert c.post(f"{A}/subscription/cancel", headers=h2).status_code == 204
    assert c.get(f"{A}/subscription", headers=h2).json()["cancel_at_period_end"] is True
    assert c.post(f"{A}/subscription/resume", headers=h2).status_code == 204
    c.post(f"{A}/subscription/cancel", headers=h2)
    with pg() as db:
        sb = db.query(Subscription).filter(Subscription.status == "active").one()
        end2 = sb.period_end if sb.period_end.tzinfo else sb.period_end.replace(tzinfo=utcnow().tzinfo)
        assert subs.tick(db, now=end2 + timedelta(hours=1))["canceled"] == 1
    assert c.post(f"{A}/subscription/cancel", headers=h).status_code == 404  # nothing to cancel


def test_renewal_notice_creates_one_order_and_one_email(shop):
    c, pg, h, _ = shop
    pay_order(c, buy_plan(c, h))
    mailer.outbox.clear()
    with pg() as db:
        sb = db.query(Subscription).one()
        end = sb.period_end if sb.period_end.tzinfo else sb.period_end.replace(tzinfo=utcnow().tzinfo)
        near = end - timedelta(days=2)
        assert subs.tick(db, now=near)["renewal_orders"] == 1
        assert subs.tick(db, now=near + timedelta(hours=1))["renewal_orders"] == 0
        assert db.query(PaymentOrder).filter(PaymentOrder.idempotency_key.like("renew:%")).count() == 1
    assert len([m for m in mailer.outbox if "segera berakhir" in m.subject]) == 1
    # a canceled subscription gets no renewal reminder
    h2 = login(c, pg, "nr@x.id")
    pay_order(c, buy_plan(c, h2, key="nr-key-000001"))
    c.post(f"{A}/subscription/cancel", headers=h2)
    with pg() as db:
        assert subs.tick(db, now=near)["renewal_orders"] == 0


def test_pending_orders_expire(shop):
    c, pg, h, _ = shop
    buy_package(c, h)
    with pg() as db:
        assert subs.tick(db, now=utcnow() + timedelta(days=2))["orders_expired"] == 1
        assert db.query(PaymentOrder).one().status == "expired"


# ---------------------------------------------------------------- admin
def test_reconcile_recovers_a_lost_webhook_exactly_once(shop):
    c, pg, h, _ = shop
    root = login(c, pg, "root@x.id", "super_admin")
    o = buy_package(c, h)
    gateway_says(o["order_no"], "paid", o["amount_idr"])  # customer paid, our webhook never arrived
    assert total(c, h) == D("10.00")
    assert c.post(f"{A}/admin/orders/{o['order_no']}/reconcile", headers=h).status_code == 403
    assert c.post(f"{A}/admin/orders/{o['order_no']}/reconcile", headers=root).json()["result"] == "processed"
    assert c.post(f"{A}/admin/orders/{o['order_no']}/reconcile", headers=root).json()["result"] == "ignored:already_fulfilled"
    assert total(c, h) == D("120.00")
    assert c.post(f"{A}/admin/orders/NOPE/reconcile", headers=root).status_code == 404


def test_admin_manages_plans_and_packages_with_price_history_and_audit(shop):
    c, pg, h, _ = shop
    root = login(c, pg, "root@x.id", "super_admin")
    assert c.get(f"{A}/admin/plans", headers=h).status_code == 403
    o = buy_plan(c, h)  # created at 49.000
    pid = next(p["id"] for p in c.get(f"{A}/admin/plans", headers=root).json() if p["code"] == "starter")
    up = c.patch(f"{A}/admin/plans/{pid}", json={"monthly_price_idr": 59000, "credits_monthly": 120}, headers=root).json()
    assert up["prices"]["monthly"] == 59000 and up["credits_monthly"] == "120.00"
    assert c.get(f"{A}/plans").json()[0]["prices"]["monthly"] == 59000
    assert c.get(f"{A}/orders/{o['order_no']}", headers=h).json()["amount_idr"] == 49000  # existing order keeps its price
    assert c.patch(f"{A}/admin/plans/{pid}", json={"monthly_price_idr": 5}, headers=root).status_code == 422
    assert c.post(f"{A}/admin/plans", json={"code": "starter", "name": "Dup", "credits_monthly": 1}, headers=root).status_code == 409
    new = c.post(f"{A}/admin/credit-packages", json={"name": "500 Kredit", "credits": 500, "price_idr": 150000}, headers=root).status_code
    assert new == 201 and len(c.get(f"{A}/credit-packages").json()) == 2
    c.patch(f"{A}/admin/plans/{pid}", json={"active": False}, headers=root)
    assert c.post(f"{A}/checkout/subscription", json={"plan_code": "starter", "cycle": "monthly"}, headers={**h, "Idempotency-Key": "inactive-k-01"}).status_code == 404
    with pg() as db:
        assert db.query(PlanPrice).filter_by(cycle="monthly").count() == 3  # old price rows preserved
    log = c.get(f"{A}/admin/audit-logs?action=plan.update", headers=root).json()
    assert log["total"] == 2 and log["items"][-1]["before"]["prices"]["monthly"] == 49000


def test_orders_are_private(shop):
    c, pg, h, other = shop
    o = buy_package(c, h)
    assert c.get(f"{A}/orders/{o['order_no']}", headers=other).status_code == 404
    assert c.get(f"{A}/orders", headers=other).json() == []


# ---------------------------------------------------------------- gateway adapters (mock HTTP; NOT verified against live sandboxes)
class FakeOrder:  # minimal order stand-in
    order_no, amount_idr, item_id, gateway_ref = "ORD-1", 49000, "item-1", "inv-123"


def midtrans(monkeypatch, handler):
    monkeypatch.setenv("MIDTRANS_SERVER_KEY", "SB-Mid-server-KEY")
    config.get_settings.cache_clear()
    return Midtrans(client=httpx.Client(transport=httpx.MockTransport(handler)))


def test_midtrans_signature_status_mapping_and_requests(monkeypatch):
    seen = {}

    def handler(req: httpx.Request):
        seen[req.url.path] = (req.headers["authorization"], json.loads(req.content) if req.content else None)
        if req.url.path.endswith("/snap/v1/transactions"):
            return httpx.Response(201, json={"token": "tok-1", "redirect_url": "https://pay.example/snap"})
        return httpx.Response(200, json={"order_id": "ORD-1", "status_code": "200", "gross_amount": "49000.00", "transaction_status": "settlement", "transaction_id": "t1"})

    gw = midtrans(monkeypatch, handler)
    assert gw.create_checkout(FakeOrder, "a@b.id", "Langganan") == ("tok-1", "https://pay.example/snap")
    auth, body = seen["/snap/v1/transactions"]
    assert auth == "Basic " + base64.b64encode(b"SB-Mid-server-KEY:").decode() and body["transaction_details"] == {"order_id": "ORD-1", "gross_amount": 49000}
    sig = hashlib.sha512(b"ORD-1" + b"200" + b"49000.00" + b"SB-Mid-server-KEY").hexdigest()
    good = json.dumps({"order_id": "ORD-1", "status_code": "200", "gross_amount": "49000.00", "signature_key": sig}).encode()
    assert gw.verify_webhook({}, good) is True
    tampered = json.dumps({"order_id": "ORD-1", "status_code": "200", "gross_amount": "1.00", "signature_key": sig}).encode()
    assert gw.verify_webhook({}, tampered) is False and gw.verify_webhook({}, b"not json") is False
    ev = gw.fetch_status(FakeOrder)
    assert (ev.status, ev.amount_idr, ev.order_no) == ("paid", 49000, "ORD-1")
    for ts, fraud, want in (("capture", "accept", "paid"), ("capture", "challenge", "failed"), ("pending", "", "pending"), ("expire", "", "expired"), ("deny", "", "failed"), ("cancel", "", "failed")):
        assert Midtrans._event({"order_id": "ORD-1", "transaction_status": ts, "fraud_status": fraud or "accept", "gross_amount": "1"}).status == want, ts
    config.get_settings.cache_clear()


def test_xendit_token_check_and_mapping(monkeypatch):
    monkeypatch.setenv("XENDIT_SECRET_KEY", "xnd_secret")
    monkeypatch.setenv("XENDIT_CALLBACK_TOKEN", "cb-token-123")
    config.get_settings.cache_clear()
    calls = []

    def handler(req: httpx.Request):
        calls.append((req.method, req.url.path))
        if req.method == "POST":
            return httpx.Response(200, json={"id": "inv-123", "invoice_url": "https://checkout.example/inv-123"})
        return httpx.Response(200, json={"id": "inv-123", "external_id": "ORD-1", "status": "PAID", "amount": 49000, "paid_amount": 49000})

    gw = Xendit(client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert gw.create_checkout(FakeOrder, "a@b.id", "x") == ("inv-123", "https://checkout.example/inv-123")
    assert gw.verify_webhook({"x-callback-token": "cb-token-123"}, b"{}") is True
    assert gw.verify_webhook({"x-callback-token": "wrong"}, b"{}") is False and gw.verify_webhook({}, b"{}") is False
    assert gw.fetch_status(FakeOrder).status == "paid" and ("GET", "/v2/invoices/inv-123") in calls
    for st, want in (("SETTLED", "paid"), ("EXPIRED", "expired"), ("PENDING", "pending"), ("FAILED", "failed")):
        assert Xendit._event({"id": "i", "external_id": "ORD-1", "status": st, "amount": 1}).status == want
    config.get_settings.cache_clear()


def test_unconfigured_real_gateways_refuse_and_fake_is_development_only(monkeypatch, shop):
    c, pg, h, _ = shop
    monkeypatch.delenv("MIDTRANS_SERVER_KEY", raising=False)
    monkeypatch.delenv("XENDIT_SECRET_KEY", raising=False)
    config.get_settings.cache_clear()
    for name in ("midtrans", "xendit"):
        with pytest.raises(GatewayError):
            get_gateway(name)
    assert c.post(f"{A}/webhooks/midtrans", content=b"{}").status_code == 503
    # the fake gateway (which would let anyone forge a payment) must not exist outside development
    o = buy_package(c, h)
    assert c.post(f"{A}/dev/fake-pay/{o['order_no']}", headers=h).status_code == 200
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "prod-secret-for-this-test")
    config.get_settings.cache_clear()
    with pytest.raises(GatewayError):
        get_gateway("fake")
    h = login(c, pg, "buyer@x.id")  # fresh token: production mode signs with SECRET_KEY
    assert c.post(f"{A}/dev/fake-pay/{o['order_no']}", headers=h).status_code == 404
    assert c.post(f"{A}/webhooks/fake", content=b"{}").status_code == 503
    config.get_settings.cache_clear()
