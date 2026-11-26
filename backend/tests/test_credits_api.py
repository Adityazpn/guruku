PW = "correct-horse-battery"


def login(c, email="a@example.com"):
    c.post("/api/v1/auth/register", json={"email": email, "password": PW})
    t = c.post("/api/v1/auth/login", json={"email": email, "password": PW}).json()["access_token"]
    return {"Authorization": f"Bearer {t}"}


def test_new_user_gets_trial_credits_once(client):
    h = login(client)
    s = client.get("/api/v1/credits/summary", headers=h).json()
    assert float(s["bonus"]) == 10.0 and float(s["total"]) == 10.0
    assert s["next_expiry"] is not None
    led = client.get("/api/v1/credits/ledger", headers=h).json()
    assert led["total"] == 1 and led["items"][0]["type"] == "bonus"
    # asking again must not grant again
    assert float(client.get("/api/v1/credits/summary", headers=h).json()["total"]) == 10.0


def test_credits_require_auth_and_are_isolated(client):
    assert client.get("/api/v1/credits/summary").status_code == 401
    ha, hb = login(client, "a@example.com"), login(client, "b@example.com")
    assert client.get("/api/v1/credits/ledger", headers=ha).json()["total"] == 1
    assert client.get("/api/v1/credits/ledger", headers=hb).json()["total"] == 1
    ids = {client.get("/api/v1/credits/ledger", headers=h).json()["items"][0]["id"] for h in (ha, hb)}
    assert len(ids) == 2


def test_ledger_pagination_bounds(client):
    h = login(client)
    assert client.get("/api/v1/credits/ledger?page_size=1000", headers=h).status_code == 422
    assert client.get("/api/v1/credits/ledger?page=0", headers=h).status_code == 422
