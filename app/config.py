from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# The SQLite journal modes Atlas supports; interpolated into a PRAGMA, so
# never widen this to a free string.
SqliteJournalMode = Literal["wal", "delete"]


class Settings(BaseSettings):
    """Application configuration, overridable via ATLAS_* environment variables.

    Loaded from real environment variables and (in dev) a gitignored `.env`;
    a real env var always wins over `.env`. `.env.example` is the source of
    truth for which variables exist: a new field needs a matching, commented
    entry there in the same commit.
    """

    model_config = SettingsConfigDict(
        env_prefix="ATLAS_",
        env_file=".env",
        extra="ignore",
        hide_input_in_errors=True,
    )

    database_url: str = "sqlite+aiosqlite:///./data/atlas.db"
    db_echo: bool = False
    # Fernet key file for stored connector credentials; created on first use, keep with the DB.
    secret_key_file: Path = Path("data/atlas.key")
    # SQLite journal mode: WAL on a local disk; Compose forces "delete" on its
    # bind mount, where WAL's memory-mapped -shm file isn't reliable.
    sqlite_journal_mode: SqliteJournalMode = "wal"

    # Connector keys and the advisor model are stored encrypted in the
    # database, entered on the Connectors page — not settings.

    # Run a draft -> critique -> revise loop inside every advice request
    # (~3x LLM cost and latency). Off by default.
    advisor_self_critique: bool = False
    # Hard bounds on one advisor LLM call: the reply's token budget (a reply
    # cut off at it fails the request) and the HTTP timeout in seconds.
    # Raise both for a wordier or reasoning model.
    advisor_max_tokens: int = Field(default=4096, ge=256, le=200_000)
    advisor_timeout_seconds: float = Field(default=120.0, gt=0, le=900)

    # Removed by ADR-0032; read only so startup can warn that it is ignored.
    mcp_token: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
