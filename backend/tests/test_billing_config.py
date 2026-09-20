"""Stripe settings are optional while billing is off, and the webhook is gated (#58)."""

import os
import subprocess
import sys

import pytest
from pydantic import ValidationError

from asr_backend import billing
from asr_backend.settings import Settings, settings

STRIPE_SETTINGS = (
    "stripe_secret_key",
    "stripe_publishable_key",
    "stripe_webhook_secret",
    "stripe_price_id",
)
VALID_STRIPE = {
    "stripe_secret_key": "sk_test_123",
    "stripe_publishable_key": "pk_test_123",
    "stripe_webhook_secret": "whsec_123",
    "stripe_price_id": "price_123",
}


def _build_settings(**overrides) -> Settings:
    """Settings from explicit values only: no .env file, and no Stripe value
    picked up from the environment unless the test passes it."""
    values = {
        "database_url": "postgresql+psycopg://user:pw@localhost/db",
        "test_database_url": "postgresql+psycopg://user:pw@localhost/db",
        "anthropic_api_key": "sk-ant-test",
        "jwt_secret_key": "jwt-secret",
        **dict.fromkeys(STRIPE_SETTINGS),
        **overrides,
    }
    return Settings(_env_file=None, **values)


# --- The webhook route -------------------------------------------------------------


@pytest.fixture
def no_stripe_settings(monkeypatch):
    for name in STRIPE_SETTINGS:
        monkeypatch.setattr(settings, name, None)
    billing.get_stripe_gateway.cache_clear()
    yield
    billing.get_stripe_gateway.cache_clear()


def test_webhook_is_a_404_while_billing_is_off(client, monkeypatch, no_stripe_settings):
    monkeypatch.setattr(settings, "billing_enabled", False)

    response = client.post(
        "/billing/webhook", content=b"{}", headers={"stripe-signature": "anything"}
    )

    assert response.status_code == 404


def test_webhook_404s_before_any_stripe_setting_is_needed(client, monkeypatch, no_stripe_settings):
    """With billing off and no Stripe settings, the route must not try to build a gateway."""
    monkeypatch.setattr(settings, "billing_enabled", False)

    response = client.post("/billing/webhook", content=b"{}")

    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}


def test_webhook_answers_again_once_billing_is_on(client, monkeypatch):
    monkeypatch.setattr(settings, "billing_enabled", True)
    monkeypatch.setattr(settings, "stripe_secret_key", "sk_test_123")
    monkeypatch.setattr(settings, "stripe_webhook_secret", "whsec_123")
    monkeypatch.setattr(settings, "stripe_price_id", "price_123")
    billing.get_stripe_gateway.cache_clear()

    response = client.post(
        "/billing/webhook", content=b"{}", headers={"stripe-signature": "not-a-signature"}
    )
    billing.get_stripe_gateway.cache_clear()

    assert response.status_code == 400


def test_the_gateway_says_so_plainly_if_stripe_is_not_configured(no_stripe_settings):
    with pytest.raises(RuntimeError, match="Stripe is not configured"):
        billing.get_stripe_gateway()


# --- Settings ------------------------------------------------------------------------


def test_stripe_settings_are_optional_while_billing_is_off():
    loaded = _build_settings(billing_enabled=False)

    assert loaded.billing_enabled is False
    assert loaded.stripe_secret_key is None


def test_billing_is_off_by_default():
    assert _build_settings().billing_enabled is False


def test_the_webhook_secret_format_is_not_checked_while_billing_is_off():
    loaded = _build_settings(billing_enabled=False, stripe_webhook_secret="anything")

    assert loaded.stripe_webhook_secret == "anything"


def test_billing_on_with_all_four_stripe_settings_loads():
    loaded = _build_settings(billing_enabled=True, **VALID_STRIPE)

    assert loaded.billing_enabled is True


@pytest.mark.parametrize("missing", STRIPE_SETTINGS)
def test_billing_on_fails_startup_naming_a_missing_setting(missing):
    with pytest.raises(ValidationError) as excinfo:
        _build_settings(billing_enabled=True, **{**VALID_STRIPE, missing: None})

    message = str(excinfo.value)
    assert "BILLING_ENABLED is true" in message
    assert missing.upper() in message


def test_billing_on_names_every_missing_setting_at_once():
    with pytest.raises(ValidationError) as excinfo:
        _build_settings(billing_enabled=True, stripe_secret_key="sk_test_123")

    message = str(excinfo.value)
    for name in ("STRIPE_PUBLISHABLE_KEY", "STRIPE_WEBHOOK_SECRET", "STRIPE_PRICE_ID"):
        assert name in message
    assert "STRIPE_SECRET_KEY" not in message


def test_billing_on_treats_a_blank_value_as_missing():
    with pytest.raises(ValidationError) as excinfo:
        _build_settings(billing_enabled=True, **{**VALID_STRIPE, "stripe_price_id": "   "})

    assert "STRIPE_PRICE_ID" in str(excinfo.value)


def test_billing_on_rejects_a_webhook_secret_without_the_whsec_prefix():
    with pytest.raises(ValidationError) as excinfo:
        _build_settings(
            billing_enabled=True, **{**VALID_STRIPE, "stripe_webhook_secret": "sk_test_oops"}
        )

    message = str(excinfo.value)
    assert "STRIPE_WEBHOOK_SECRET must start with 'whsec_'" in message


def test_the_app_fails_to_start_with_billing_on_and_stripe_unset(tmp_path):
    """The real startup path: env vars in, process out, with the message on stderr."""
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("STRIPE_") and key != "BILLING_ENABLED"
    }
    env.update(
        BILLING_ENABLED="true",
        DATABASE_URL="postgresql+psycopg://user:pw@localhost/db",
        TEST_DATABASE_URL="postgresql+psycopg://user:pw@localhost/db",
        ANTHROPIC_API_KEY="sk-ant-test",
        JWT_SECRET_KEY="jwt-secret",
    )

    result = subprocess.run(
        [sys.executable, "-c", "import asr_backend.main"],
        cwd=tmp_path,  # no .env file here
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )

    assert result.returncode != 0
    assert "BILLING_ENABLED is true" in result.stderr
    assert "STRIPE_SECRET_KEY" in result.stderr


def test_the_app_starts_with_billing_off_and_no_stripe_settings(tmp_path):
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("STRIPE_") and key != "BILLING_ENABLED"
    }
    env.update(
        DATABASE_URL="postgresql+psycopg://user:pw@localhost/db",
        TEST_DATABASE_URL="postgresql+psycopg://user:pw@localhost/db",
        ANTHROPIC_API_KEY="sk-ant-test",
        JWT_SECRET_KEY="jwt-secret",
    )

    result = subprocess.run(
        [sys.executable, "-c", "import asr_backend.main"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )

    assert result.returncode == 0, result.stderr
