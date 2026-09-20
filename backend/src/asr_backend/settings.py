from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    test_database_url: str
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
    stripe_secret_key: str
    stripe_publishable_key: str
    stripe_webhook_secret: str
    stripe_price_id: str


settings = Settings()
