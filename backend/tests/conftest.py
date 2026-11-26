import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.admin.models
import app.ai_engine.models
import app.ai_providers.models
import app.auth.models
import app.credits.models
import app.credits.pricing_models
import app.documents.models
import app.users.models
from app.core import email as mailer
from app.core import rate_limit as rl
from app.core.db import Base, get_db
from main import app


@pytest.fixture
def db_session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(engine, expire_on_commit=False)
    s = Session()
    yield s
    s.close()


@pytest.fixture
def client(db_session):
    rl.reset()
    mailer.outbox.clear()
    def override():
        yield db_session

    app.dependency_overrides[get_db] = override
    yield TestClient(app)
    app.dependency_overrides.clear()


# ---------- PostgreSQL fixtures (credit ledger needs real row locks and triggers) ----------
import os  # noqa: E402

PG_URL = os.environ.get("TEST_DATABASE_URL")


@pytest.fixture(scope="session")
def pg_engine():
    if not PG_URL:
        pytest.skip("TEST_DATABASE_URL not set; PostgreSQL tests skipped")
    from alembic import command
    from alembic.config import Config

    cfg = Config("alembic.ini")
    cfg.attributes["url"] = PG_URL
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")  # real migrations => triggers exist
    engine = create_engine(PG_URL, pool_size=40, max_overflow=20)
    yield engine
    engine.dispose()


@pytest.fixture
def pg(pg_engine):
    """Returns a session factory; every table is emptied before each test."""
    from sqlalchemy import text

    with pg_engine.begin() as c:
        names = [t.name for t in Base.metadata.sorted_tables]
        c.execute(text("ALTER TABLE credit_transactions DISABLE TRIGGER credit_ledger_no_update"))
        c.execute(text("TRUNCATE " + ", ".join(names) + " RESTART IDENTITY CASCADE"))
        c.execute(text("ALTER TABLE credit_transactions ENABLE TRIGGER credit_ledger_no_update"))
    return sessionmaker(pg_engine, expire_on_commit=False)


@pytest.fixture
def pg_client(pg, monkeypatch):
    """HTTP client backed by PostgreSQL; AI jobs run inline instead of in a background worker."""
    rl.reset()
    mailer.outbox.clear()

    def override():
        with pg() as s:
            yield s

    def inline(request_id, background):
        from app.ai_engine import engine

        with pg() as s:
            engine.process(s, request_id, sleep=lambda _: None)

    monkeypatch.setattr("app.ai_engine.dispatch.dispatch", inline)
    app.dependency_overrides[get_db] = override
    yield TestClient(app)
    app.dependency_overrides.clear()
