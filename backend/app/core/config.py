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


@lru_cache
def get_settings() -> Settings:
    return Settings()
