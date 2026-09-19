import pytest
from conftest import TEST_DATABASE_LOCK_ID, acquire_test_database_lock, test_engine
from sqlalchemy import text


def test_database_is_locked_against_parallel_pytest_processes():
    with test_engine.connect() as connection:
        acquired = connection.scalar(
            text("SELECT pg_try_advisory_lock(:lock_id)"),
            {"lock_id": TEST_DATABASE_LOCK_ID},
        )
        if acquired:
            connection.execute(
                text("SELECT pg_advisory_unlock(:lock_id)"),
                {"lock_id": TEST_DATABASE_LOCK_ID},
            )

    assert acquired is False


def test_waiting_for_the_database_lock_gives_up_with_a_clear_message():
    # The session fixture already holds the lock, so this second session must wait.
    with (
        test_engine.connect() as connection,
        pytest.raises(pytest.exit.Exception, match="another pytest run"),
    ):
        acquire_test_database_lock(connection, timeout_seconds=0.2, poll_seconds=0.05)


def test_waiting_for_the_database_lock_says_so_once(monkeypatch):
    monkeypatch.setattr("conftest.TEST_DATABASE_LOCK_ANNOUNCE_SECONDS", 0.1)
    messages = []

    with test_engine.connect() as connection, pytest.raises(pytest.exit.Exception):
        acquire_test_database_lock(
            connection,
            timeout_seconds=0.5,
            poll_seconds=0.05,
            announce=messages.append,
        )

    assert messages == ["Waiting for another pytest run to release the test database..."]
