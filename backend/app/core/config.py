from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All secrets come from the environment. No defaults for real credentials."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    database_url: str = "postgresql+psycopg://app:app@localhost:5432/app"
    redis_url: str = "redis://localhost:6379/0"
    secret_key: str = ""  # JWT signing; must be set outside development
    provider_key_master: str = ""  # master key for encrypting provider API keys at rest
    s3_endpoint: str = ""
    s3_bucket: str = "documents"
    app_base_url: str = "http://localhost:3000"
    smtp_host: str = ""  # empty => emails are only recorded in-process (dev/test)
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    mail_from: str = "no-reply@example.com"
    rate_limit_enabled: bool = True
    payment_gateway: str = "fake"  # fake (development only) | midtrans | xendit
    midtrans_server_key: str = ""
    midtrans_production: bool = False
    xendit_secret_key: str = ""
    xendit_callback_token: str = ""
    fake_gateway_secret: str = "dev-only-fake-gateway-secret"
    grace_days: int = 3
    renewal_notice_days: int = 3
    admin_mfa_required: bool = True
    allowed_origins: str = ""  # comma-separated extra origins allowed to call cookie endpoints (APP_BASE_URL is always allowed)
    queue_mode: str = "background"  # background (dev, in-process) | celery (production worker)


@lru_cache
def get_settings() -> Settings:
    return Settings()
