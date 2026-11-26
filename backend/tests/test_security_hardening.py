import pyotp
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth.service import get_or_create_role
from app.core import config
from app.users.models import User, UserRole
from main import app

PW = "correct-horse-battery"
A = "/api/v1"


# ---------------------------------------------------------------- CSRF on cookie endpoints
def test_cookie_endpoints_reject_requests_without_the_csrf_header_or_from_foreign_origins(client):
    client.post(f"{A}/auth/register", json={"email": "a@x.id", "password": PW})
    client.post(f"{A}/auth/login", json={"email": "a@x.id", "password": PW})
    plain = TestClient(app)  # no X-Requested-With, like a cross-site HTML form post
    plain.cookies.update(client.cookies)
    assert plain.post(f"{A}/auth/refresh").status_code == 403
    assert plain.post(f"{A}/auth/logout").status_code == 403
    foreign = client.post(f"{A}/auth/refresh", headers={"Origin": "https://evil.example"})
    assert foreign.status_code == 403 and foreign.json()["detail"] == "csrf_blocked"
    assert client.post(f"{A}/auth/refresh", headers={"Origin": config.get_settings().app_base_url}).status_code == 200
    assert client.post(f"{A}/auth/refresh").status_code == 200  # same-site fetch without Origin header is fine


def test_security_headers_present(client):
    r = client.get(f"{A}/health")
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"] and r.headers["cache-control"] == "no-store"
    assert "strict-transport-security" not in r.headers  # development only; enabled elsewhere


def test_hsts_outside_development(client, monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "x" * 40)
    config.get_settings.cache_clear()
    assert "max-age=31536000" in client.get(f"{A}/health").headers["strict-transport-security"]


# ---------------------------------------------------------------- MFA
@pytest.fixture
def mfa_env(monkeypatch):
    monkeypatch.setenv("ADMIN_MFA_REQUIRED", "true")
    monkeypatch.setenv("PROVIDER_KEY_MASTER", "test-master")
    config.get_settings.cache_clear()


def make_admin(c, pg, email="boss@x.id"):
    c.post(f"{A}/auth/register", json={"email": email, "password": PW})
    with pg() as db:
        u = db.scalar(select(User).where(User.email == email))
        u.roles.append(UserRole(user_id=u.id, role=get_or_create_role(db, "super_admin")))
        db.commit()


def tok(c, email="boss@x.id", totp=None):
    r = c.post(f"{A}/auth/login", json={"email": email, "password": PW, **({"totp": totp} if totp else {})})
    return r, ({"Authorization": f"Bearer {r.json()['access_token']}"} if r.status_code == 200 else None)


def test_admin_routes_need_mfa_and_enrolment_works(pg_client, pg, mfa_env):
    c = pg_client
    make_admin(c, pg)
    _, h = tok(c)
    assert c.get(f"{A}/admin/providers", headers=h).json()["detail"] == "mfa_required"  # password alone is not enough
    assert c.get(f"{A}/me", headers=h).json()["mfa_enabled"] is False
    setup = c.post(f"{A}/auth/mfa/setup", headers=h).json()
    assert setup["otpauth_uri"].startswith("otpauth://totp/") and len(setup["secret"]) >= 16
    assert c.post(f"{A}/auth/mfa/confirm", json={"code": "000000"}, headers=h).status_code == 400
    totp = pyotp.TOTP(setup["secret"])
    assert c.post(f"{A}/auth/mfa/confirm", json={"code": totp.now()}, headers=h).status_code == 204
    assert c.get(f"{A}/admin/providers", headers=h).json()["detail"] == "mfa_required"  # old session was password-only
    assert c.post(f"{A}/auth/mfa/setup", headers=h).status_code == 409
    r, _ = tok(c)
    assert r.status_code == 401 and r.json()["detail"] == "mfa_required"  # now login demands the code
    r, _ = tok(c, totp="123456")
    assert r.status_code == 401 and r.json()["detail"] == "invalid_credentials"
    r, h2 = tok(c, totp=totp.now())
    assert r.status_code == 200 and c.get(f"{A}/admin/providers", headers=h2).status_code == 200
    # the refresh token keeps the second-factor state
    refreshed = c.post(f"{A}/auth/refresh").json()["access_token"]
    assert c.get(f"{A}/admin/providers", headers={"Authorization": f"Bearer {refreshed}"}).status_code == 200


def test_secret_is_encrypted_and_wrong_codes_lock_the_account(pg_client, pg, mfa_env):
    c = pg_client
    make_admin(c, pg)
    _, h = tok(c)
    secret = c.post(f"{A}/auth/mfa/setup", headers=h).json()["secret"]
    c.post(f"{A}/auth/mfa/confirm", json={"code": pyotp.TOTP(secret).now()}, headers=h)
    with pg() as db:
        assert secret not in db.scalar(select(User.mfa_secret_enc).where(User.email == "boss@x.id"))
    for _ in range(5):
        tok(c, totp="000000")
    assert tok(c, totp=pyotp.TOTP(secret).now())[0].status_code == 423  # locked even with a valid code


def test_non_admins_are_unaffected_by_mfa_requirement(pg_client, pg, mfa_env):
    c = pg_client
    c.post(f"{A}/auth/register", json={"email": "t@x.id", "password": PW})
    r, h = tok(c, "t@x.id")
    assert r.status_code == 200 and c.get(f"{A}/me", headers=h).status_code == 200
    assert c.get(f"{A}/admin/providers", headers=h).json()["detail"] == "forbidden"
