import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from asr_backend.db import Base, get_db
from asr_backend.main import app
from asr_backend.settings import settings

test_engine = create_engine(settings.test_database_url)
TestSessionLocal = sessionmaker(bind=test_engine, autoflush=False, autocommit=False)


@pytest.fixture(autouse=True)
def _reset_db():
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)
    yield


@pytest.fixture(autouse=True)
def _full_text_storage(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "full_text_storage_path", str(tmp_path / "full_texts"))


@pytest.fixture
def client():
    def _get_test_db():
        db = TestSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _get_test_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def auth_headers_for(client, email: str) -> dict[str, str]:
    """Registers (if needed) and logs in `email`, returning its auth header.

    Shared by tests that need more than one distinct Reviewer identity (e.g.
    an owner and a non-owner) to check #24's ownership scoping.
    """
    client.post("/register", json={"email": email, "password": "correcthorse"})
    token = client.post(
        "/login", json={"email": email, "password": "correcthorse"}
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def authed_client(client):
    """A client pre-authenticated as its own Reviewer, for endpoints gated by #24.

    Tests exercising the gate itself (missing/invalid token, wrong-owner
    access) use the plain `client` fixture and manage tokens explicitly.
    """
    headers = auth_headers_for(client, "owner@example.com")
    client.headers["Authorization"] = headers["Authorization"]
    return client


@pytest.fixture
def db_session():
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()
