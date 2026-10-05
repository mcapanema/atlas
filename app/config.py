import re
from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# The MCP token is a URL path segment and the endpoint's only credential:
# secrets.token_urlsafe(24) yields 32 of these characters.
_MCP_TOKEN = re.compile(r"[A-Za-z0-9_-]{24,}")


class Settings(BaseSettings):
    """Application configuration, overridable via ATLAS_* environment variables.

    Loaded from real environment variables and (in dev) a gitignored `.env`;
    a real env var always wins over `.env`. `.env.example` is the source of
    truth for which variables exist: a new field needs a matching, commented
    entry there in the same commit.
    """

    model_config = SettingsConfigDict(env_prefix="ATLAS_", env_file=".env", extra="ignore")

    database_url: str = "sqlite+aiosqlite:///./atlas.db"
    db_echo: bool = False

    # Linear personal API key; None/empty disables the Linear connector.
    linear_api_key: str | None = None

    # OpenRouter API key; None/empty disables the AI advisor.
    openrouter_api_key: str | None = None
    # OpenRouter model slug the advisor uses.
    advisor_model: str = "anthropic/claude-sonnet-5"
    # Run a draft -> critique -> revise loop inside every advice request
    # (~3x LLM cost and latency). Off by default.
    advisor_self_critique: bool = False

    # Secret path token for the MCP endpoint (/mcp/<token>); None/empty
    # disables MCP chat access entirely (no route is mounted).
    mcp_token: str | None = None

    @field_validator("mcp_token")
    @classmethod
    def _mcp_token_is_a_strong_path_segment(cls, value: str | None) -> str | None:
        """Refuse a guessable or path-unsafe token at startup instead of serving it.

        Empty or unset disables MCP. Anything else must be 24+ URL-safe
        characters: a `{…}` would become a Starlette path parameter (the
        mount would match every token), a `/` a second path segment.
        """
        if value and not _MCP_TOKEN.fullmatch(value):
            raise ValueError(
                "ATLAS_MCP_TOKEN must be at least 24 characters of A-Z, a-z, 0-9, '_' or '-'"
            )
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
