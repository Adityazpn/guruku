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
    queue_mode: str = "background"  # background (dev, in-process) | celery (production worker)


@lru_cache
def get_settings() -> Settings:
    return Settings()
