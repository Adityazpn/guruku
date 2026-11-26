import json
import logging
from datetime import timedelta

from sqlalchemy import update

from app.ai_engine.models import AiRequest
from app.core import config
from app.core.db import utcnow
from tests.aihelpers import TP_INPUT, make_user, setup_ai
from tests.test_admin import login

A = "/api/v1"


def test_health_is_minimal_and_ready_checks_the_database(client, db_session, monkeypatch):
    assert client.get(f"{A}/health").json() == {"status": "ok"}
    r = client.get(f"{A}/ready")
    assert r.status_code in (200, 503) and "database" in r.json()["checks"]


def test_every_response_carries_a_request_id_and_it_is_honoured(client):
    r = client.get(f"{A}/health")
    assert len(r.headers["x-request-id"]) >= 8
    assert client.get(f"{A}/health", headers={"X-Request-ID": "abc-123"}).headers["x-request-id"] == "abc-123"


def test_json_logs_never_contain_secrets_or_bodies(client, caplog):
    caplog.set_level(logging.INFO)
    client.post(f"{A}/auth/login", json={"email": "x@x.id", "password": "SuperSecretPassword1"})
    text = " ".join(r.getMessage() + json.dumps(getattr(r, "__dict__", {}), default=str) for r in caplog.records)
    assert "SuperSecretPassword1" not in text and "x@x.id" not in text and "/api/v1/auth/login" in text


def test_system_health_flags_stuck_work_and_needs_an_admin(pg_client, pg):
    c = pg_client
    admin, teacher = login(c, pg, "a@x.id", "ai_admin"), login(c, pg, "t@x.id")
    assert c.get(f"{A}/admin/system", headers=teacher).status_code == 403
    assert c.get(f"{A}/admin/system", headers=admin).json()["alerts"] == []
    with pg() as db:
        setup_ai(db)
        u, _ = make_user(db, "u@x.id")
        db.commit()
        from app.ai_engine import engine as eng
        rid = eng.submit(db, u.id, "tp-generator", TP_INPUT, "stuck-key-0001").id
        db.execute(update(AiRequest).where(AiRequest.id == rid).values(created_at=utcnow() - timedelta(minutes=10)))
        db.commit()
    s = c.get(f"{A}/admin/system", headers=admin).json()
    assert s["stats"]["ai_queued_over_5min"] == 1 and any("worker" in a.lower() for a in s["alerts"])


def test_config_defaults_are_safe(monkeypatch):
    monkeypatch.delenv("ADMIN_MFA_REQUIRED", raising=False)  # the suite relaxes it globally; check the real default
    s = config.Settings(_env_file=None)
    assert s.admin_mfa_required is True and s.payment_gateway == "fake" and s.app_env == "development"
