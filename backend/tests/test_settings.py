"""Settings a deployed app needs and does not need (#65)."""

import pytest

from asr_backend.settings import Settings


def _build_settings(**overrides) -> Settings:
    values = {
        "database_url": "postgresql+psycopg://localhost/db",
        "anthropic_api_key": "sk-ant-test",
        "jwt_secret_key": "jwt-secret",
        **overrides,
    }
    return Settings(_env_file=None, **values)


def test_a_deployed_app_does_not_need_a_test_database(monkeypatch):
    monkeypatch.delenv("TEST_DATABASE_URL", raising=False)

    assert _build_settings().test_database_url is None


@pytest.mark.parametrize("provided", ["postgresql://host:5432/db", "postgres://host/db"])
def test_a_plain_postgres_url_from_a_host_uses_the_psycopg_driver(provided):
    built = _build_settings(database_url=provided, test_database_url=provided)

    expected = "postgresql+psycopg://" + provided.split("://", 1)[1]
    assert built.database_url == expected
    assert built.test_database_url == expected


def test_a_url_that_already_names_a_driver_is_left_alone():
    url = "postgresql+psycopg://host/db?sslmode=require"

    assert _build_settings(database_url=url).database_url == url
