import re

from app.core import email as mailer
from app.core import rate_limit as rl
from app.users.models import User

PW = "correct-horse-battery"


def token_from_last_mail():
    return re.search(r"token=([\w-]+)", mailer.outbox[-1].body).group(1)


def reg(c, email="a@example.com"):
    return c.post("/api/v1/auth/register", json={"email": email, "password": PW})


def auth(c, email="a@example.com", pw=PW):
    t = c.post("/api/v1/auth/login", json={"email": email, "password": pw}).json()["access_token"]
    return {"Authorization": f"Bearer {t}"}


def test_verify_email_flow(client, db_session):
    reg(client)
    assert mailer.outbox[-1].to == "a@example.com"
    assert client.get("/api/v1/me", headers=auth(client)).json()["email_verified"] is False
    tok = token_from_last_mail()
    assert client.post("/api/v1/auth/verify-email", json={"token": tok}).status_code == 204
    assert client.get("/api/v1/me", headers=auth(client)).json()["email_verified"] is True
    # single use
    assert client.post("/api/v1/auth/verify-email", json={"token": tok}).status_code == 400
    assert client.post("/api/v1/auth/verify-email", json={"token": "x" * 30}).status_code == 400


def test_token_is_stored_hashed(client, db_session):
    reg(client)
    from app.auth.models import EmailToken
    assert db_session.query(EmailToken).one().token_hash != token_from_last_mail()


def test_forgot_password_does_not_leak_and_reset_works(client, db_session):
    reg(client)
    mailer.outbox.clear()
    assert client.post("/api/v1/auth/forgot-password", json={"email": "ghost@example.com"}).status_code == 204
    assert mailer.outbox == []
    assert client.post("/api/v1/auth/forgot-password", json={"email": "a@example.com"}).status_code == 204
    tok = token_from_last_mail()
    # an active session exists before reset
    client.post("/api/v1/auth/login", json={"email": "a@example.com", "password": PW})
    new_pw = "brand-new-password-1"
    assert client.post("/api/v1/auth/reset-password", json={"token": tok, "new_password": new_pw}).status_code == 204
    assert client.post("/api/v1/auth/refresh").status_code == 401  # sessions revoked
    assert client.post("/api/v1/auth/login", json={"email": "a@example.com", "password": PW}).status_code == 401
    assert client.post("/api/v1/auth/login", json={"email": "a@example.com", "password": new_pw}).status_code == 200
    assert client.post("/api/v1/auth/reset-password", json={"token": tok, "new_password": new_pw}).status_code == 400


def test_new_reset_invalidates_old_one(client):
    reg(client)
    client.post("/api/v1/auth/forgot-password", json={"email": "a@example.com"})
    first = token_from_last_mail()
    client.post("/api/v1/auth/forgot-password", json={"email": "a@example.com"})
    r = client.post("/api/v1/auth/reset-password", json={"token": first, "new_password": "another-password-1"})
    assert r.status_code == 400


def test_rate_limit_forgot_password(client):
    codes = [client.post("/api/v1/auth/forgot-password", json={"email": "a@example.com"}).status_code for _ in range(7)]
    assert codes[:5] == [204] * 5 and codes[5] == 429


def test_profile_roundtrip_and_isolation(client):
    reg(client)
    reg(client, "b@example.com")
    ha, hb = auth(client), auth(client, "b@example.com")
    body = {"school_name": "SDN 1", "education_levels": ["SD"], "subjects": ["Matematika"]}
    assert client.put("/api/v1/me/profile", json=body, headers=ha).status_code == 200
    assert client.get("/api/v1/me/profile", headers=ha).json()["school_name"] == "SDN 1"
    assert client.get("/api/v1/me/profile", headers=hb).json()["school_name"] == ""
    assert client.get("/api/v1/me/profile").status_code == 401
