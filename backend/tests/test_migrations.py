"""Alembic migrations run up and down against a real Postgres (#60).

They run in a scratch schema on the test database, through the connection hook
in migrations/env.py, so the configured database and the tables the other tests
use are never touched.
"""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from conftest import test_engine
from sqlalchemy import text

SCHEMA = "asr_migration_test"
BEFORE_INVITED_ONLY = "a3f7c9d2b1e4"
INVITED_ONLY = "c7e1a94d2f30"


@pytest.fixture
def migrations():
    """An Alembic config bound to a connection whose search_path is a scratch schema."""
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    with test_engine.connect() as connection:
        connection.execute(text(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE"))
        connection.execute(text(f"CREATE SCHEMA {SCHEMA}"))
        connection.execute(text(f"SET search_path TO {SCHEMA}"))
        connection.commit()
        config.attributes["connection"] = connection
        try:
            yield config, connection
        finally:
            connection.rollback()
            connection.execute(text("SET search_path TO public"))
            connection.execute(text(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE"))
            connection.commit()


def _invited_only_column(connection):
    return connection.execute(
        text(
            "SELECT is_nullable, column_default FROM information_schema.columns "
            "WHERE table_schema = :schema AND table_name = 'reviewers' "
            "AND column_name = 'invited_only'"
        ),
        {"schema": SCHEMA},
    ).one_or_none()


def _upgrade(config, connection, revision):
    command.upgrade(config, revision)
    connection.commit()


def _downgrade(config, connection, revision):
    command.downgrade(config, revision)
    connection.commit()


def test_every_migration_applies_from_an_empty_database_and_back_out(migrations):
    config, connection = migrations

    _upgrade(config, connection, "head")
    _downgrade(config, connection, "base")

    tables = connection.execute(
        text(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = :schema AND table_name <> 'alembic_version'"
        ),
        {"schema": SCHEMA},
    ).all()
    assert tables == []


def test_invited_only_is_added_not_null_and_false_for_existing_reviewers(migrations):
    config, connection = migrations
    _upgrade(config, connection, BEFORE_INVITED_ONLY)
    assert _invited_only_column(connection) is None
    connection.execute(
        text(
            "INSERT INTO reviewers (id, email, hashed_password, created_at) "
            "VALUES (gen_random_uuid(), 'existing@example.com', 'x', now())"
        )
    )
    connection.commit()

    _upgrade(config, connection, INVITED_ONLY)

    is_nullable, column_default = _invited_only_column(connection)
    assert is_nullable == "NO"
    assert column_default == "false"
    existing = connection.execute(text("SELECT invited_only FROM reviewers")).scalar_one()
    assert existing is False


def test_invited_only_downgrade_drops_the_column_and_keeps_the_reviewers(migrations):
    config, connection = migrations
    _upgrade(config, connection, INVITED_ONLY)
    connection.execute(
        text(
            "INSERT INTO reviewers (id, email, hashed_password, created_at, invited_only) "
            "VALUES (gen_random_uuid(), 'invitee@example.com', 'x', now(), true)"
        )
    )
    connection.commit()

    _downgrade(config, connection, BEFORE_INVITED_ONLY)

    assert _invited_only_column(connection) is None
    assert connection.execute(text("SELECT email FROM reviewers")).scalar_one() == (
        "invitee@example.com"
    )

    _upgrade(config, connection, INVITED_ONLY)

    assert _invited_only_column(connection) is not None
