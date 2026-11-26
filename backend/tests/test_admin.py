import json
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.admin.models import AuditLog
from app.ai_engine import engine as eng
from app.ai_engine.models import AiPromptVersion
from app.ai_engine.seed import seed_tp_tool
from app.ai_providers.adapters.fake import FakeProvider
from app.ai_providers.base import ProviderAuthError
from app.ai_providers.models import AiProviderCredential
from app.auth.service import get_or_create_role
from app.core import config
from app.core.db import utcnow
from app.credits import service as cs
from app.users.models import User, UserRole
from tests.aihelpers import TP_INPUT, VALID, reset_fake

PW = "correct-horse-battery"
SECRET = "sk-test-SUPERSECRET-9876"
A = "/api/v1/admin"


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("PROVIDER_KEY_MASTER", "test-master")
    config.get_settings.cache_clear()
    reset_fake()
    monkeypatch.setattr(eng, "RETRY_BACKOFF", (0, 0))
    yield
    config.get_settings.cache_clear()


def login(c, pg, email, role=None):
    c.post("/api/v1/auth/register", json={"email": email, "password": PW})
    if role:
        with pg() as db:
            u = db.scalar(select(User).where(User.email == email))
            u.roles.append(UserRole(user_id=u.id, role=get_or_create_role(db, role)))
            db.commit()
    t = c.post("/api/v1/auth/login", json={"email": email, "password": PW}).json()["access_token"]
    return {"Authorization": f"Bearer {t}"}


@pytest.fixture
def ctx(pg_client, pg):
    with pg() as db:
        seed_tp_tool(db)
        db.commit()
    c = pg_client
    return c, pg, login(c, pg, "root@x.id", "super_admin"), login(c, pg, "ai@x.id", "ai_admin"), login(c, pg, "teacher@x.id")


def tool_id(c, h):
    return c.get(f"{A}/tools", headers=h).json()[0]["id"]


# ---------------------------------------------------------------- authorization
READ_ROUTES = ["/providers", "/tools", "/ai/usage", "/users", "/audit-logs"]


@pytest.mark.parametrize("path", READ_ROUTES)
def test_anonymous_and_teachers_are_locked_out(ctx, path):
    c, pg, root, ai, teacher = ctx
    assert c.get(A + path).status_code == 401
    assert c.get(A + path, headers=teacher).status_code == 403


def test_teacher_cannot_write_anything(ctx):
    c, pg, root, ai, teacher = ctx
    tid = tool_id(c, root)
    writes = [("post", "/providers", {"code": "openai", "name": "OpenAI"}), ("post", "/fx-rates", {"rate": 16500}),
              ("patch", f"/tools/{tid}", {"is_active": False}), ("post", f"/users/{uuid.uuid4()}/credits/grant", {"amount": 5, "reason": "xx"}),
              ("put", f"/tools/{tid}/pricing-rule", {"mode": "fixed"})]
    for m, path, body in writes:
        assert getattr(c, m)(A + path, json=body, headers=teacher).status_code == 403, path


def test_ai_admin_can_manage_ai_but_not_users_credits_or_audit(ctx):
    c, pg, root, ai, teacher = ctx
    assert c.get(A + "/providers", headers=ai).status_code == 200
    assert c.get(A + "/users", headers=ai).status_code == 403
    assert c.get(A + "/audit-logs", headers=ai).status_code == 403
    assert c.post(f"{A}/users/{uuid.uuid4()}/credits/grant", json={"amount": 5, "reason": "xx"}, headers=ai).status_code == 403


# ---------------------------------------------------------------- providers & keys
def test_credential_is_write_only_encrypted_and_never_echoed_or_audited(ctx):
    c, pg, root, ai, teacher = ctx
    pid = c.post(A + "/providers", json={"code": "openai", "name": "OpenAI"}, headers=ai).json()["id"]
    assert c.patch(f"{A}/providers/{pid}", json={"status": "enabled"}, headers=ai).status_code == 409  # no key yet
    r = c.put(f"{A}/providers/{pid}/credential", json={"api_key": SECRET, "label": "prod"}, headers=ai)
    assert r.status_code == 200 and r.json()["credential"] == {"label": "prod", "last4": "9876", "status": "active"}
    assert c.patch(f"{A}/providers/{pid}", json={"status": "enabled"}, headers=ai).status_code == 200
    everything = json.dumps([c.get(A + "/providers", headers=ai).json(), r.json(), c.get(A + "/audit-logs", headers=root).json()], default=str)
    assert SECRET not in everything and "SUPERSECRET" not in everything
    with pg() as db:
        row = db.scalar(select(AiProviderCredential))
        assert SECRET not in row.secret_ciphertext
        assert SECRET not in json.dumps([(a.before, a.after) for a in db.scalars(select(AuditLog))], default=str)


def test_rotating_a_key_revokes_the_old_one(ctx):
    c, pg, root, ai, teacher = ctx
    pid = c.post(A + "/providers", json={"code": "openai", "name": "OpenAI"}, headers=ai).json()["id"]
    c.put(f"{A}/providers/{pid}/credential", json={"api_key": "sk-first-key-1111"}, headers=ai)
    c.put(f"{A}/providers/{pid}/credential", json={"api_key": "sk-second-key-2222"}, headers=ai)
    with pg() as db:
        st = {r.last4: r.status for r in db.scalars(select(AiProviderCredential))}
    assert st == {"1111": "revoked", "2222": "active"}


def test_provider_validation(ctx):
    c, pg, root, ai, teacher = ctx
    assert c.post(A + "/providers", json={"code": "skynet", "name": "Nope"}, headers=ai).status_code == 422
    assert c.post(A + "/providers", json={"code": "openai", "name": "A"}, headers=ai).status_code == 422  # name too short
    assert c.post(A + "/providers", json={"code": "openai", "name": "OpenAI"}, headers=ai).status_code == 201
    assert c.post(A + "/providers", json={"code": "openai", "name": "OpenAI"}, headers=ai).status_code == 409
    pid = c.get(A + "/providers", headers=ai).json()["providers"][0]["id"]
    assert c.put(f"{A}/providers/{pid}/credential", json={"api_key": "short"}, headers=ai).status_code == 422
    assert c.patch(f"{A}/providers/{pid}", json={"daily_spend_limit_usd": -1}, headers=ai).status_code == 422
    p = c.patch(f"{A}/providers/{pid}", json={"daily_spend_limit_usd": 5, "monthly_spend_limit_usd": 100}, headers=ai).json()
    assert (p["daily_spend_limit_usd"], p["monthly_spend_limit_usd"]) == (5.0, 100.0)
    assert c.patch(f"{A}/providers/{pid}", json={"clear_limits": True}, headers=ai).json()["daily_spend_limit_usd"] is None


def test_model_price_versioning_and_fx_sanity(ctx):
    c, pg, root, ai, teacher = ctx
    pid = c.post(A + "/providers", json={"code": "fake", "name": "Fake"}, headers=ai).json()["id"]
    p = c.post(f"{A}/providers/{pid}/models", json={"model_code": "m-1"}, headers=ai).json()
    mid = p["models"][0]["id"]
    assert c.post(f"{A}/providers/{pid}/models", json={"model_code": "m-1"}, headers=ai).status_code == 409
    assert c.post(f"{A}/models/{mid}/pricing", json={"input_per_1m": -1, "output_per_1m": 1}, headers=ai).status_code == 422
    t0 = utcnow() - timedelta(days=2)
    assert c.post(f"{A}/models/{mid}/pricing", json={"input_per_1m": 1, "output_per_1m": 4, "effective_from": t0.isoformat()}, headers=ai).status_code == 201
    r = c.post(f"{A}/models/{mid}/pricing", json={"input_per_1m": 2, "output_per_1m": 8}, headers=ai).json()
    assert r["models"][0]["pricing"]["version"] == 2 and r["models"][0]["pricing"]["input_per_1m"] == 2.0
    older = (t0 - timedelta(days=1)).isoformat()
    assert c.post(f"{A}/models/{mid}/pricing", json={"input_per_1m": 1, "output_per_1m": 1, "effective_from": older}, headers=ai).status_code == 422
    assert c.post(f"{A}/fx-rates", json={"rate": 16.5}, headers=ai).status_code == 422  # typo guard
    assert c.post(f"{A}/fx-rates", json={"rate": 16500}, headers=ai).status_code == 201
    assert c.get(A + "/providers", headers=ai).json()["fx"]["rate"] == 16500.0
    assert c.patch(f"{A}/models/{mid}", json={"status": "disabled"}, headers=ai).json()["models"][0]["status"] == "disabled"


def test_connection_test_reports_success_and_provider_errors(ctx):
    c, pg, root, ai, teacher = ctx
    pid = c.post(A + "/providers", json={"code": "fake", "name": "Fake"}, headers=ai).json()["id"]
    mid = c.post(f"{A}/providers/{pid}/models", json={"model_code": "m-1"}, headers=ai).json()["models"][0]["id"]
    FakeProvider.script = ['{"ok": true}']
    assert c.post(f"{A}/providers/{pid}/test", json={"model_id": mid}, headers=ai).json()["ok"] is True
    FakeProvider.script = [ProviderAuthError("401")]
    assert c.post(f"{A}/providers/{pid}/test", json={"model_id": mid}, headers=ai).json() == {"ok": False, "error": "provider_auth"}
    pid2 = c.post(A + "/providers", json={"code": "openai", "name": "OpenAI"}, headers=ai).json()["id"]
    assert c.post(f"{A}/providers/{pid2}/test", json={"model_id": mid}, headers=ai).status_code == 422


# ---------------------------------------------------------------- tool readiness, prompts, pricing rule: the whole flow
def configure_via_admin(c, ai, mode="fixed"):
    """Everything an owner must do before the first generation, using only the admin API."""
    tid = tool_id(c, ai)
    assert c.get(f"{A}/tools", headers=ai).json()[0]["ready"] is False
    pid = c.post(A + "/providers", json={"code": "fake", "name": "Fake"}, headers=ai).json()["id"]
    mid = c.post(f"{A}/providers/{pid}/models", json={"model_code": "m-1"}, headers=ai).json()["models"][0]["id"]
    c.post(f"{A}/models/{mid}/pricing", json={"input_per_1m": 1, "output_per_1m": 4, "effective_from": (utcnow() - timedelta(days=1)).isoformat()}, headers=ai)
    c.post(f"{A}/fx-rates", json={"rate": 16500, "effective_from": (utcnow() - timedelta(days=1)).isoformat()}, headers=ai)
    c.patch(f"{A}/providers/{pid}", json={"status": "enabled"}, headers=ai)
    c.put(f"{A}/tools/{tid}/assignments", json={"model_ids": [mid]}, headers=ai)
    rule = {"mode": mode, "fixed_credits": 3, "min_credits": 1, "max_credits": 20, "margin_pct": 300, "processing_fee_idr": 20}
    return tid, pid, mid, c.put(f"{A}/tools/{tid}/pricing-rule", json=rule, headers=ai).json()


def test_admin_api_alone_makes_a_tool_ready_and_usable(ctx):
    c, pg, root, ai, teacher = ctx
    tid, pid, mid, tool = configure_via_admin(c, ai)
    assert tool["ready"] is True and tool["problems"] == [] and tool["pricing_rule"]["mode"] == "fixed"
    FakeProvider.script = [VALID]
    r = c.post("/api/v1/tools/tp-generator/generate", json={"input": TP_INPUT}, headers={**teacher, "Idempotency-Key": "adm-flow-001"})
    assert r.status_code == 202
    got = c.get(f"/api/v1/ai/requests/{r.json()['id']}", headers=teacher).json()
    assert got["status"] == "succeeded" and got["credits_charged"] == "3.00"
    u = c.get(f"{A}/ai/usage", headers=ai).json()
    assert u["is_estimate"] is True and u["totals"]["requests"] == 1 and u["items"][0]["tool"] == "tp-generator"
    assert u["items"][0]["api_cost_usd"] == pytest.approx(0.009)


def test_readiness_names_what_is_missing(ctx):
    c, pg, root, ai, teacher = ctx
    t = c.get(f"{A}/tools", headers=ai).json()[0]
    assert set(t["problems"]) == {"no_pricing_rule", "no_enabled_model"}
    pid = c.post(A + "/providers", json={"code": "fake", "name": "Fake"}, headers=ai).json()["id"]
    mid = c.post(f"{A}/providers/{pid}/models", json={"model_code": "m-1"}, headers=ai).json()["models"][0]["id"]
    c.patch(f"{A}/providers/{pid}", json={"status": "enabled"}, headers=ai)
    tid = t["id"]
    c.put(f"{A}/tools/{tid}/assignments", json={"model_ids": [mid]}, headers=ai)
    t = c.put(f"{A}/tools/{tid}/pricing-rule", json={"mode": "dynamic", "min_credits": 1, "max_credits": 20}, headers=ai).json()
    assert set(t["problems"]) == {"no_fx_rate", "no_model_price"}  # dynamic needs real prices; says exactly what to add
    assert c.put(f"{A}/tools/{tid}/assignments", json={"model_ids": [str(uuid.uuid4())]}, headers=ai).status_code == 422


def test_pricing_rule_validation_and_versioning(ctx):
    c, pg, root, ai, teacher = ctx
    tid = tool_id(c, ai)
    put = lambda b: c.put(f"{A}/tools/{tid}/pricing-rule", json=b, headers=ai)  # noqa: E731
    assert put({"mode": "dynamic", "min_credits": 10, "max_credits": 5}).status_code == 422
    assert put({"mode": "fixed", "fixed_credits": 50, "min_credits": 1, "max_credits": 20}).status_code == 422
    assert put({"mode": "weird"}).status_code == 422
    assert put({"mode": "dynamic", "credit_value_idr": 0}).status_code == 422
    assert put({"mode": "fixed", "fixed_credits": 2, "min_credits": 1, "max_credits": 10}).json()["pricing_rule"]["version"] == 1
    assert put({"mode": "fixed", "fixed_credits": 4, "min_credits": 1, "max_credits": 10}).json()["pricing_rule"]["version"] == 2


def test_prompt_versions_are_immutable_publishable_and_rollbackable(ctx):
    c, pg, root, ai, teacher = ctx
    tid, *_ = configure_via_admin(c, ai)
    prompts = lambda: c.get(f"{A}/tools/{tid}/prompts", headers=ai).json()  # noqa: E731
    assert [(p["version"], p["status"]) for p in prompts()] == [(1, "published")]
    bad = {"system_prompt": "Sistem prompt yang cukup panjang.", "user_template": "Halo {{ input.topic "}
    assert c.post(f"{A}/tools/{tid}/prompts", json=bad, headers=ai).status_code == 422
    good = {"system_prompt": "Anda asisten guru. Balas JSON saja.", "user_template": "VERSI-DUA: {{ input.topic }}\n{{ input_json }}", "change_note": "v2"}
    v2 = c.post(f"{A}/tools/{tid}/prompts", json=good, headers=ai).json()
    assert v2["version"] == 2 and v2["status"] == "draft"
    # a draft is not live yet: generation still uses v1
    FakeProvider.script = [VALID, VALID, VALID]
    gen = lambda k: c.post("/api/v1/tools/tp-generator/generate", json={"input": TP_INPUT}, headers={**teacher, "Idempotency-Key": k})  # noqa: E731
    gen("prompt-test-01")
    assert "VERSI-DUA" not in FakeProvider.calls[-1].user
    assert c.post(f"{A}/prompts/{v2['id']}/publish", headers=ai).status_code == 200
    assert sorted((p["version"], p["status"]) for p in prompts()) == [(1, "archived"), (2, "published")]
    gen("prompt-test-02")
    assert "VERSI-DUA" in FakeProvider.calls[-1].user
    old = next(p for p in prompts() if p["version"] == 1)
    assert c.post(f"{A}/prompts/{old['id']}/publish", headers=ai).status_code == 409  # archived rows are never revived in place
    rb = c.post(f"{A}/tools/{tid}/prompts/rollback", json={"version": 1}, headers=ai).json()
    assert rb["version"] == 3 and rb["status"] == "published" and "rollback to v1" in rb["change_note"]
    gen("prompt-test-03")
    assert "VERSI-DUA" not in FakeProvider.calls[-1].user
    with pg() as db:  # nothing was edited in place: 3 distinct rows
        assert db.query(AiPromptVersion).count() == 3
    assert c.post(f"{A}/tools/{tid}/prompts/rollback", json={"version": 99}, headers=ai).status_code == 404


def test_disabling_a_tool_takes_effect_immediately(ctx):
    c, pg, root, ai, teacher = ctx
    tid, *_ = configure_via_admin(c, ai)
    assert c.patch(f"{A}/tools/{tid}", json={"is_active": False}, headers=ai).json()["is_active"] is False
    assert c.get("/api/v1/tools", headers=teacher).json() == []
    assert c.patch(f"{A}/tools/{tid}", json={"est_output_tokens": 0}, headers=ai).status_code == 422


# ---------------------------------------------------------------- credits grant & audit
def test_grant_credits_is_super_admin_only_validated_and_audited(ctx):
    c, pg, root, ai, teacher = ctx
    uid = c.get(f"{A}/users?q=teacher", headers=root).json()[0]["id"]
    assert c.get(f"{A}/users?q=teacher", headers=root).json()[0]["credits"] == "10.00"
    g = lambda b: c.post(f"{A}/users/{uid}/credits/grant", json=b, headers=root)  # noqa: E731
    assert g({"amount": 0, "reason": "x y z"}).status_code == 422
    assert g({"amount": 5, "reason": ""}).status_code == 422
    assert g({"amount": 5, "reason": "kompensasi gangguan"}).json()["total"] == "15.00"
    assert c.post(f"{A}/users/{uuid.uuid4()}/credits/grant", json={"amount": 5, "reason": "xxx"}, headers=root).status_code == 404
    with pg() as db:
        u = db.scalar(select(User).where(User.email == "teacher@x.id"))
        assert cs.summary(db, cs.get_or_create_wallet(db, u.id).id)["total"] == 15
    log = c.get(f"{A}/audit-logs?action=credits.grant", headers=root).json()
    assert log["total"] == 1 and log["items"][0]["after"]["reason"] == "kompensasi gangguan" and log["items"][0]["actor_id"]


def test_audit_log_records_actor_before_after_and_is_append_only(ctx):
    c, pg, root, ai, teacher = ctx
    tid = tool_id(c, ai)
    c.patch(f"{A}/tools/{tid}", json={"est_output_tokens": 999}, headers=ai)
    items = c.get(f"{A}/audit-logs?action=tool.update", headers=root).json()["items"]
    assert items[0]["before"]["est_output_tokens"] == 1200 and items[0]["after"]["est_output_tokens"] == 999
    with pg() as db:
        ai_id = str(db.scalar(select(User).where(User.email == "ai@x.id")).id)
    assert items[0]["actor_id"] == ai_id
    for stmt in ("UPDATE audit_logs SET action = 'x'", "DELETE FROM audit_logs"):
        with pg() as db, pytest.raises(DBAPIError, match="append-only"):
            db.execute(text(stmt))
