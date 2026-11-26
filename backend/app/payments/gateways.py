"""Payment gateway abstraction. Each gateway can: create a checkout, verify a webhook's authenticity, parse it, and
re-fetch the transaction status from the gateway's API (the server-side truth we act on, never the webhook body alone).

Midtrans and Xendit adapters follow those providers' documented REST/webhook shapes as understood at writing time and are
tested only against mock HTTP; they MUST be verified against the current official docs and sandbox before real money flows."""
import base64
import hashlib
import hmac
import json
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal

import httpx

from app.core.config import get_settings


@dataclass
class GatewayEvent:
    event_id: str
    order_no: str
    status: str  # paid | pending | failed | expired
    amount_idr: int
    txn_id: str | None = None
    method: str = ""


class GatewayError(Exception):
    pass


def _idr(v) -> int:
    return int(Decimal(str(v)))  # "49000.00" -> 49000


class Midtrans:
    name = "midtrans"

    def __init__(self, client: httpx.Client | None = None):
        s = get_settings()
        self.key = s.midtrans_server_key
        self.snap = "https://app.midtrans.com" if s.midtrans_production else "https://app.sandbox.midtrans.com"
        self.api = "https://api.midtrans.com" if s.midtrans_production else "https://api.sandbox.midtrans.com"
        self.http = client or httpx.Client(timeout=20)
        if not self.key:
            raise GatewayError("MIDTRANS_SERVER_KEY not configured")

    def _auth(self):
        return {"Authorization": "Basic " + base64.b64encode(f"{self.key}:".encode()).decode(), "Accept": "application/json"}

    def create_checkout(self, order, email: str, description: str):
        r = self.http.post(f"{self.snap}/snap/v1/transactions", headers=self._auth(), json={
            "transaction_details": {"order_id": order.order_no, "gross_amount": order.amount_idr},
            "customer_details": {"email": email}, "item_details": [{"id": str(order.item_id), "price": order.amount_idr, "quantity": 1, "name": description[:50]}]})
        if r.status_code not in (200, 201):
            raise GatewayError(f"midtrans {r.status_code}")
        d = r.json()
        return d["token"], d["redirect_url"]

    def verify_webhook(self, headers: Mapping, body: bytes) -> bool:
        try:
            d = json.loads(body)
            raw = f"{d['order_id']}{d['status_code']}{d['gross_amount']}{self.key}"
            return hmac.compare_digest(hashlib.sha512(raw.encode()).hexdigest(), str(d.get("signature_key", "")))
        except (ValueError, KeyError, TypeError):
            return False

    @staticmethod
    def _event(d: dict) -> GatewayEvent:
        ts, fraud = d.get("transaction_status", ""), d.get("fraud_status", "accept")
        status = "paid" if (ts == "settlement" or (ts == "capture" and fraud == "accept")) else "pending" if ts == "pending" else "expired" if ts == "expire" else "failed"
        return GatewayEvent(event_id=f"{d.get('transaction_id', d['order_id'])}:{ts}:{d.get('status_code', '')}", order_no=d["order_id"], status=status,
                            amount_idr=_idr(d.get("gross_amount", 0)), txn_id=d.get("transaction_id"), method=d.get("payment_type", ""))

    def parse_webhook(self, body: bytes) -> GatewayEvent:
        return self._event(json.loads(body))

    def fetch_status(self, order) -> GatewayEvent | None:
        r = self.http.get(f"{self.api}/v2/{order.order_no}/status", headers=self._auth())
        if r.status_code == 404:
            return None
        if r.status_code != 200:
            raise GatewayError(f"midtrans status {r.status_code}")
        return self._event(r.json())


class Xendit:
    name = "xendit"

    def __init__(self, client: httpx.Client | None = None):
        s = get_settings()
        self.key, self.token = s.xendit_secret_key, s.xendit_callback_token
        self.base = "https://api.xendit.co"
        self.http = client or httpx.Client(timeout=20)
        if not (self.key and self.token):
            raise GatewayError("XENDIT_SECRET_KEY / XENDIT_CALLBACK_TOKEN not configured")

    def _auth(self):
        return {"Authorization": "Basic " + base64.b64encode(f"{self.key}:".encode()).decode()}

    def create_checkout(self, order, email: str, description: str):
        r = self.http.post(f"{self.base}/v2/invoices", headers=self._auth(), json={
            "external_id": order.order_no, "amount": order.amount_idr, "payer_email": email, "description": description[:200], "currency": "IDR"})
        if r.status_code not in (200, 201):
            raise GatewayError(f"xendit {r.status_code}")
        d = r.json()
        return d["id"], d["invoice_url"]

    def verify_webhook(self, headers: Mapping, body: bytes) -> bool:
        got = headers.get("x-callback-token", "")
        return bool(self.token) and hmac.compare_digest(got.encode(), self.token.encode())

    @staticmethod
    def _event(d: dict) -> GatewayEvent:
        st = d.get("status", "")
        status = "paid" if st in ("PAID", "SETTLED") else "expired" if st == "EXPIRED" else "pending" if st == "PENDING" else "failed"
        return GatewayEvent(event_id=f"{d['id']}:{st}", order_no=d["external_id"], status=status, amount_idr=_idr(d.get("paid_amount") or d.get("amount", 0)),
                            txn_id=d.get("payment_id") or d.get("id"), method=d.get("payment_method", ""))

    def parse_webhook(self, body: bytes) -> GatewayEvent:
        return self._event(json.loads(body))

    def fetch_status(self, order) -> GatewayEvent | None:
        if not order.gateway_ref:
            return None
        r = self.http.get(f"{self.base}/v2/invoices/{order.gateway_ref}", headers=self._auth())
        if r.status_code == 404:
            return None
        if r.status_code != 200:
            raise GatewayError(f"xendit status {r.status_code}")
        return self._event(r.json())


class Fake:
    """Development/test gateway. `STATUS` plays the role of the real gateway's server-side truth. Refuses to exist in production."""

    name = "fake"
    STATUS: dict[str, GatewayEvent] = {}

    def __init__(self, client=None):
        s = get_settings()
        if s.app_env not in ("development", "test"):
            raise GatewayError("fake gateway is not available outside development")
        self.secret = s.fake_gateway_secret.encode()

    def sign(self, body: bytes) -> str:
        return hmac.new(self.secret, body, hashlib.sha256).hexdigest()

    def create_checkout(self, order, email: str, description: str):
        return f"fake-{order.order_no}", f"{get_settings().app_base_url}/fake-pay?order={order.order_no}"

    def verify_webhook(self, headers: Mapping, body: bytes) -> bool:
        return hmac.compare_digest(self.sign(body), headers.get("x-fake-signature", ""))

    def parse_webhook(self, body: bytes) -> GatewayEvent:
        d = json.loads(body)
        return GatewayEvent(d["event_id"], d["order_no"], d["status"], int(d["amount_idr"]), d.get("txn_id"), "fake")

    def fetch_status(self, order) -> GatewayEvent | None:
        return Fake.STATUS.get(order.order_no)


def get_gateway(name: str | None = None, client=None):
    name = name or get_settings().payment_gateway
    cls = {"midtrans": Midtrans, "xendit": Xendit, "fake": Fake}.get(name)
    if cls is None:
        raise GatewayError(f"unknown gateway {name}")
    return cls(client=client)
