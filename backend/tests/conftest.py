import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.auth.models
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
