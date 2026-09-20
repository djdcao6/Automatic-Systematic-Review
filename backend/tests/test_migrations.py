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
from sqlalchemy.exc import IntegrityError

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


# --- Unique active Extraction Field names (#67) --------------------------------------------

UNIQUE_FIELD_NAMES = "e4b7c2d9a1f6"
FIELD_INDEX = "uq_extraction_fields_active_name"


def _seed_project(connection, email: str) -> str:
    """A Review Project (and its owner) as they exist just before the index migration."""
    owner_id = connection.execute(
        text(
            "INSERT INTO reviewers (id, email, hashed_password, created_at) "
            "VALUES (gen_random_uuid(), :email, 'x', now()) RETURNING id"
        ),
        {"email": email},
    ).scalar_one()
    return str(
        connection.execute(
            text(
                "INSERT INTO review_projects "
                "(id, name, owner_reviewer_id, criteria_locked, merge_mode, review_mode, "
                "created_at) VALUES (gen_random_uuid(), 'P', :owner, false, 'combine', "
                "'solo', now()) RETURNING id"
            ),
            {"owner": owner_id},
        ).scalar_one()
    )


def _seed_field(connection, project_id: str, name: str, archived: bool = False) -> None:
    connection.execute(
        text(
            "INSERT INTO extraction_fields "
            "(id, review_project_id, name, archived, created_at, updated_at) "
            "VALUES (gen_random_uuid(), :project, :name, :archived, now(), now())"
        ),
        {"project": project_id, "name": name, "archived": archived},
    )


def _field_index_exists(connection) -> bool:
    return (
        connection.execute(
            text("SELECT 1 FROM pg_indexes WHERE schemaname = :schema AND indexname = :name"),
            {"schema": SCHEMA, "name": FIELD_INDEX},
        ).scalar()
        is not None
    )


def _current_revision(connection) -> str:
    return connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()


def test_the_unique_name_index_is_added_when_there_are_no_duplicates(migrations):
    config, connection = migrations
    _upgrade(config, connection, INVITED_ONLY)
    project = _seed_project(connection, "a@example.com")
    other_project = _seed_project(connection, "b@example.com")
    _seed_field(connection, project, "Sample size")
    _seed_field(connection, project, "Follow-up")
    # None of these are duplicates the index would refuse: another project, an
    # archived copy of an active name, and a name that differs inside.
    _seed_field(connection, other_project, "Sample size")
    _seed_field(connection, project, "sample SIZE", archived=True)
    _seed_field(connection, project, "sample  size")
    connection.commit()

    _upgrade(config, connection, UNIQUE_FIELD_NAMES)

    assert _field_index_exists(connection)
    assert connection.execute(text("SELECT count(*) FROM extraction_fields")).scalar_one() == 5


def test_the_unique_name_migration_stops_with_a_list_when_duplicates_exist(migrations):
    config, connection = migrations
    _upgrade(config, connection, INVITED_ONLY)
    project = _seed_project(connection, "a@example.com")
    other_project = _seed_project(connection, "b@example.com")
    _seed_field(connection, project, "Sample size")
    _seed_field(connection, project, " sample SIZE ")
    _seed_field(connection, other_project, "Outcome")
    _seed_field(connection, other_project, "OUTCOME")
    _seed_field(connection, other_project, "Fine")
    connection.commit()

    with pytest.raises(RuntimeError) as excinfo:
        _upgrade(config, connection, UNIQUE_FIELD_NAMES)
    connection.rollback()

    message = str(excinfo.value)
    assert "Rename or archive" in message
    assert project in message and other_project in message
    assert "'Sample size'" in message and "' sample SIZE '" in message
    assert "'Outcome'" in message and "'OUTCOME'" in message
    assert "Fine" not in message
    # Nothing was changed: no index, still at the earlier revision, every row kept.
    assert not _field_index_exists(connection)
    assert _current_revision(connection) == INVITED_ONLY
    assert connection.execute(text("SELECT count(*) FROM extraction_fields")).scalar_one() == 5


def test_the_migration_goes_ahead_once_the_duplicates_are_fixed(migrations):
    config, connection = migrations
    _upgrade(config, connection, INVITED_ONLY)
    project = _seed_project(connection, "a@example.com")
    _seed_field(connection, project, "Sample size")
    _seed_field(connection, project, "sample size")
    connection.commit()
    with pytest.raises(RuntimeError):
        _upgrade(config, connection, UNIQUE_FIELD_NAMES)
    connection.rollback()

    connection.execute(
        text("UPDATE extraction_fields SET archived = true WHERE name = 'sample size'")
    )
    connection.commit()
    _upgrade(config, connection, UNIQUE_FIELD_NAMES)

    assert _field_index_exists(connection)


def test_the_index_refuses_an_active_duplicate_and_allows_an_archived_one(migrations):
    config, connection = migrations
    _upgrade(config, connection, UNIQUE_FIELD_NAMES)
    project = _seed_project(connection, "a@example.com")
    _seed_field(connection, project, "Sample size")
    connection.commit()

    _seed_field(connection, project, "SAMPLE SIZE", archived=True)
    connection.commit()
    with pytest.raises(IntegrityError):
        _seed_field(connection, project, "  sample size ")
    connection.rollback()


def test_the_unique_name_downgrade_drops_the_index_and_keeps_the_fields(migrations):
    config, connection = migrations
    _upgrade(config, connection, UNIQUE_FIELD_NAMES)
    project = _seed_project(connection, "a@example.com")
    _seed_field(connection, project, "Sample size")
    connection.commit()

    _downgrade(config, connection, INVITED_ONLY)

    assert not _field_index_exists(connection)
    assert connection.execute(text("SELECT count(*) FROM extraction_fields")).scalar_one() == 1
    # With the index gone, duplicates can be written again, and the way back up
    # then refuses them with the list rather than failing partway.
    _seed_field(connection, project, "sample size")
    connection.commit()
    with pytest.raises(RuntimeError, match="Rename or archive"):
        _upgrade(config, connection, UNIQUE_FIELD_NAMES)
    connection.rollback()
