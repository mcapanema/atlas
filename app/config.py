from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration, overridable via ATLAS_* environment variables."""

    model_config = SettingsConfigDict(env_prefix="ATLAS_", env_file=".env", extra="ignore")

    database_url: str = "sqlite+aiosqlite:///./atlas.db"
    db_echo: bool = False

    # Linear personal API key; None/empty disables the Linear connector.
    linear_api_key: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
