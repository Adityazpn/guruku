import uuid
from decimal import Decimal as D

import pytest

from app.ai_engine import engine as eng
from app.ai_providers.adapters.fake import FakeProvider
from tests.aihelpers import TP_INPUT, VALID, reset_fake, setup_ai

PW = "correct-horse-battery"


@pytest.fixture(autouse=True)
def _fake(monkeypatch):
    reset_fake()
    monkeypatch.setattr(eng, "RETRY_BACKOFF", (0, 0))


def user(c, email="a@example.com"):
    c.post("/api/v1/auth/register", json={"email": email, "password": PW})  # also grants 10 trial credits
    t = c.post("/api/v1/auth/login", json={"email": email, "password": PW}).json()["access_token"]
    return {"Authorization": f"Bearer {t}"}


@pytest.fixture
def ready(pg_client, pg):
    with pg() as db:
        setup_ai(db)
        db.commit()
    return pg_client


def gen(c, h, key=None, body=None):
    return c.post("/api/v1/tools/tp-generator/generate", json={"input": body or TP_INPUT},
                  headers={**h, "Idempotency-Key": key or str(uuid.uuid4())})


def test_requires_login(ready):
    assert ready.get("/api/v1/tools").status_code == 401
    assert ready.post("/api/v1/tools/tp-generator/generate", json={"input": {}}).status_code == 401


def test_catalogue_and_schema(ready):
    h = user(ready)
    tools = ready.get("/api/v1/tools", headers=h).json()
    assert [t["slug"] for t in tools] == ["tp-generator"]
    assert "education_level" in ready.get("/api/v1/tools/tp-generator", headers=h).json()["input_schema"]["properties"]
    assert ready.get("/api/v1/tools/nope", headers=h).status_code == 404


def test_estimate_shows_cost_before_generating(ready):
    h = user(ready)
    e = ready.post("/api/v1/tools/tp-generator/estimate", headers=h).json()
    assert e["mode"] == "dynamic" and D(e["min"]) <= D(e["expected"]) <= D(e["max"])
    assert D(e["balance"]) == D("10.00") and e["sufficient"] is True


def test_generate_end_to_end_and_charges_once(ready):
    h = user(ready)
    FakeProvider.script = [VALID]
    r = gen(ready, h, key="idem-key-0001")
    assert r.status_code == 202
    again = gen(ready, h, key="idem-key-0001")  # retry from a flaky network
    assert again.json()["id"] == r.json()["id"]
    got = ready.get(f"/api/v1/ai/requests/{r.json()['id']}", headers=h).json()
    assert got["status"] == "succeeded" and got["output"]["tujuan_pembelajaran"]
    assert D(got["credits_charged"]) == D("3.00")
    assert D(ready.get("/api/v1/credits/summary", headers=h).json()["total"]) == D("7.00")
    assert len(FakeProvider.calls) == 1


def test_failed_generation_costs_the_user_nothing(ready):
    h = user(ready)
    FakeProvider.script = ["garbage", "garbage"]
    r = gen(ready, h).json()
    got = ready.get(f"/api/v1/ai/requests/{r['id']}", headers=h).json()
    assert got["status"] == "failed" and got["error_code"] == "malformed_output" and got["output"] is None
    assert D(ready.get("/api/v1/credits/summary", headers=h).json()["total"]) == D("10.00")


def test_validation_and_idempotency_header(ready):
    h = user(ready)
    assert ready.post("/api/v1/tools/tp-generator/generate", json={"input": TP_INPUT}, headers=h).status_code == 400
    assert gen(ready, h, body={"topic": "x"}).status_code == 422
    assert gen(ready, h, body={**TP_INPUT, "evil": "extra"}).status_code == 422  # additionalProperties=false


def test_402_when_out_of_credits(ready, pg):
    h = user(ready)
    FakeProvider.script = [VALID] * 10
    codes = [gen(ready, h).status_code for _ in range(6)]  # 3 credits each, 10 available
    assert codes[:3] == [202, 202, 202] and codes[3] == 402


def test_other_users_cannot_read_a_request(ready):
    a, b = user(ready, "a@example.com"), user(ready, "b@example.com")
    FakeProvider.script = [VALID]
    rid = gen(ready, a).json()["id"]
    assert ready.get(f"/api/v1/ai/requests/{rid}", headers=b).status_code == 404
    assert ready.get(f"/api/v1/ai/requests/{uuid.uuid4()}", headers=a).status_code == 404


def test_inactive_tool_hidden(ready, pg):
    h = user(ready)
    from app.ai_engine.models import AiTool
    with pg() as db:
        db.query(AiTool).update({"is_active": False})
        db.commit()
    assert ready.get("/api/v1/tools", headers=h).json() == []
    assert gen(ready, h).status_code == 404
