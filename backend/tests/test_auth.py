from app.auth.models import UserSession
from app.core.deps import require_roles
from fastapi import Depends
from main import app

PW = "correct-horse-battery"


def reg(c, email="a@example.com"):
    return c.post("/api/v1/auth/register", json={"email": email, "password": PW, "full_name": "A"})


def login(c, email="a@example.com", pw=PW):
    return c.post("/api/v1/auth/login", json={"email": email, "password": pw})


def test_register_login_me(client):
    assert reg(client).status_code == 201
    r = login(client)
    assert r.status_code == 200
    me = client.get("/api/v1/me", headers={"Authorization": f"Bearer {r.json()['access_token']}"})
    assert me.json()["roles"] == ["user"]
    assert "httponly" in r.headers["set-cookie"].lower()


def test_password_stored_as_argon2id(client, db_session):
    reg(client)
    from app.users.models import User
    assert db_session.query(User).one().password_hash.startswith("$argon2id$")


def test_duplicate_and_weak_password(client):
    reg(client)
    assert reg(client, "A@Example.com").status_code == 409
    assert client.post("/api/v1/auth/register", json={"email": "b@example.com", "password": "short"}).status_code == 422


def test_wrong_password_and_unknown_user_same_error(client):
    reg(client)
    a, b = login(client, pw="nope-nope-nope"), login(client, "ghost@example.com")
    assert a.status_code == b.status_code == 401
    assert a.json() == b.json()


def test_lockout_after_failures(client):
    reg(client)
    for _ in range(5):
        login(client, pw="wrong-wrong-wrong")
    assert login(client).status_code == 423


def test_protected_requires_token(client):
    assert client.get("/api/v1/me").status_code == 401
    assert client.get("/api/v1/me", headers={"Authorization": "Bearer junk"}).status_code == 401


def test_refresh_rotation_and_reuse_detection(client, db_session):
    reg(client)
    login(client)
    old = client.cookies.get("refresh_token")
    r = client.post("/api/v1/auth/refresh")
    assert r.status_code == 200
    new = client.cookies.get("refresh_token")
    assert new and new != old
    # replay the rotated (old) token: must fail and revoke everything
    client.cookies.clear()
    client.cookies.set("refresh_token", old, path="/api/v1/auth")
    assert client.post("/api/v1/auth/refresh").json()["detail"] == "refresh_reuse_detected"
    assert all(s.revoked_at for s in db_session.query(UserSession))
    client.cookies.clear()
    client.cookies.set("refresh_token", new, path="/api/v1/auth")
    assert client.post("/api/v1/auth/refresh").status_code == 401


def test_logout_revokes(client):
    reg(client)
    login(client)
    assert client.post("/api/v1/auth/logout").status_code == 204
    assert client.post("/api/v1/auth/refresh").status_code == 401


def test_rbac(client, db_session):
    @app.get("/_admin_only", dependencies=[Depends(require_roles("super_admin"))])
    def _admin():
        return {"ok": True}

    reg(client)
    tok = login(client).json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    assert client.get("/_admin_only", headers=h).status_code == 403
    from app.auth.service import get_or_create_role
    from app.users.models import User, UserRole
    u = db_session.query(User).one()
    u.roles.append(UserRole(user_id=u.id, role=get_or_create_role(db_session, "super_admin")))
    db_session.commit()
    assert client.get("/_admin_only", headers=h).status_code == 200
