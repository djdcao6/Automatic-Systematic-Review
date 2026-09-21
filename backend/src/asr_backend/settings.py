from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_STRIPE_SETTING_NAMES = (
    "stripe_secret_key",
    "stripe_publishable_key",
    "stripe_webhook_secret",
    "stripe_price_id",
)
_WEBHOOK_SECRET_PREFIX = "whsec_"
_PSYCOPG_URL_PREFIX = "postgresql+psycopg://"
# What hosts hand out. SQLAlchemy reads postgresql:// as the psycopg2 driver, which is not
# installed, and does not recognise postgres:// at all.
_PLAIN_POSTGRES_URL_PREFIXES = ("postgres://", "postgresql://")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    # Only the test suite needs this (it resets the database it points at), so a
    # deployed app neither has to set it nor can be pointed at it by accident.
    test_database_url: str | None = None
    frontend_origin: str = "http://localhost:3000"
    anthropic_api_key: str
    anthropic_model: str = "claude-haiku-4-5"
    full_text_storage_path: str = "./storage/full_texts"
    jwt_secret_key: str
    # Emails allowed to register, comma-separated. Empty means nobody (see signup.py).
    signup_allowlist: str = ""
    # Reverse proxies in front of the app. Used to find the caller's address for
    # the login and sign-up rate limits; leave at 0 when nothing is in front.
    trusted_proxy_count: int = 0
    billing_enabled: bool = False
    # Only needed once billing_enabled is true; see require_stripe_when_billing_is_on.
    stripe_secret_key: str | None = None
    stripe_publishable_key: str | None = None
    stripe_webhook_secret: str | None = None
    stripe_price_id: str | None = None

    @field_validator("database_url", "test_database_url")
    @classmethod
    def use_the_psycopg_driver(cls, url: str | None) -> str | None:
        """Accepts the plain postgresql:// URL a host provides, e.g. Render's connectionString."""
        if url is None:
            return url
        for prefix in _PLAIN_POSTGRES_URL_PREFIXES:
            if url.startswith(prefix):
                return _PSYCOPG_URL_PREFIX + url[len(prefix):]
        return url

    @model_validator(mode="after")
    def require_stripe_when_billing_is_on(self) -> "Settings":
        """Fails startup, with the setting names, rather than at the first Stripe call."""
        if not self.billing_enabled:
            return self
        missing = [
            name.upper() for name in _STRIPE_SETTING_NAMES if not (getattr(self, name) or "").strip()
        ]
        if missing:
            raise ValueError(
                "BILLING_ENABLED is true, so these settings must be set: " + ", ".join(missing)
            )
        if not self.stripe_webhook_secret.startswith(_WEBHOOK_SECRET_PREFIX):
            raise ValueError(
                f"STRIPE_WEBHOOK_SECRET must start with '{_WEBHOOK_SECRET_PREFIX}'. "
                "Use the signing secret of the webhook endpoint from the Stripe dashboard."
            )
        return self


settings = Settings()
