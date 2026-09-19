import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from asr_backend.db import Base, get_db
from asr_backend.main import app
from asr_backend.settings import settings

test_engine = create_engine(settings.test_database_url)
TestSessionLocal = sessionmaker(bind=test_engine, autoflush=False, autocommit=False)
TEST_DATABASE_LOCK_ID = 0x415352  # "ASR"
TEST_DATABASE_LOCK_TIMEOUT_SECONDS = 15 * 60
TEST_DATABASE_LOCK_POLL_SECONDS = 0.5
TEST_DATABASE_LOCK_ANNOUNCE_SECONDS = 5


def acquire_test_database_lock(
    connection,
    *,
    timeout_seconds=TEST_DATABASE_LOCK_TIMEOUT_SECONDS,
    poll_seconds=TEST_DATABASE_LOCK_POLL_SECONDS,
    announce=lambda message: None,
):
    """Polls for the session lock so a stuck holder fails loudly instead of hanging."""
    started = time.monotonic()
    announced = False
    while not connection.scalar(
        text("SELECT pg_try_advisory_lock(:lock_id)"),
        {"lock_id": TEST_DATABASE_LOCK_ID},
    ):
        waited = time.monotonic() - started
        if waited >= timeout_seconds:
            pytest.exit(
                f"Gave up after {timeout_seconds:g}s waiting for another pytest run "
                "to release the test database.",
                returncode=3,
            )
        if not announced and waited >= TEST_DATABASE_LOCK_ANNOUNCE_SECONDS:
            announce("Waiting for another pytest run to release the test database...")
            announced = True
        time.sleep(poll_seconds)


@pytest.fixture(scope="session", autouse=True)
def _serialize_test_database_access(request):
    """Keep concurrent pytest processes from resetting the same database."""
    reporter = request.config.pluginmanager.get_plugin("terminalreporter")
    announce = reporter.write_line if reporter else (lambda message: None)
    # AUTOCOMMIT keeps the lock connection out of "idle in transaction", so a
    # server-side idle_in_transaction_session_timeout cannot silently drop the lock.
    with test_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        acquire_test_database_lock(connection, announce=announce)
        try:
            yield
        finally:
            connection.execute(
                text("SELECT pg_advisory_unlock(:lock_id)"),
                {"lock_id": TEST_DATABASE_LOCK_ID},
            )


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
