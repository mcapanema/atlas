from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config import Settings

# Scrubbed from the real environment so a developer's shell or CI can't
# leak into assertions.
_VARS = ("ATLAS_DATABASE_URL", "ATLAS_DB_ECHO", "ATLAS_ADVISOR_MODEL", "ATLAS_MCP_TOKEN")


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in _VARS:
        monkeypatch.delenv(var, raising=False)


def test_defaults_apply_without_env() -> None:
    settings = Settings(_env_file=None)

    assert settings.database_url == "sqlite+aiosqlite:///./atlas.db"
    assert settings.db_echo is False
    assert settings.advisor_model == "anthropic/claude-sonnet-5"


def test_prefixed_env_var_overrides_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ATLAS_DB_ECHO", "true")

    assert Settings(_env_file=None).db_echo is True


def test_unprefixed_env_var_is_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DB_ECHO", "true")

    assert Settings(_env_file=None).db_echo is False


def test_env_file_is_read(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("ATLAS_ADVISOR_MODEL=model-from-dotenv\n")

    assert Settings(_env_file=env_file).advisor_model == "model-from-dotenv"


def test_real_env_var_beats_env_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # The documented contract (Settings docstring, app/config.py): real env vars always win
    # over .env. tests/api/test_connectors.py's hermeticity relies on it.
    env_file = tmp_path / ".env"
    env_file.write_text("ATLAS_ADVISOR_MODEL=model-from-dotenv\n")
    monkeypatch.setenv("ATLAS_ADVISOR_MODEL", "model-from-env")

    assert Settings(_env_file=env_file).advisor_model == "model-from-env"


_GOOD_TOKEN = "test-token-0123456789abcdefghij"


def test_mcp_token_defaults_to_none(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(_env_file=None)

    assert settings.mcp_token is None

    monkeypatch.setenv("ATLAS_MCP_TOKEN", _GOOD_TOKEN)
    assert Settings(_env_file=None).mcp_token == _GOOD_TOKEN


def test_an_empty_mcp_token_disables_mcp(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ATLAS_MCP_TOKEN", "")

    assert Settings(_env_file=None).mcp_token == ""


@pytest.mark.parametrize(
    "token",
    [
        "sekret",  # short
        "x" * 23,  # one under the floor
        "{path}" + "x" * 30,  # Starlette would read a path parameter: matches anything
        "a/b" + "x" * 30,  # a second path segment
        "with space" + "x" * 30,
    ],
)
def test_mcp_token_must_be_a_long_url_safe_segment(
    monkeypatch: pytest.MonkeyPatch, token: str
) -> None:
    monkeypatch.setenv("ATLAS_MCP_TOKEN", token)

    with pytest.raises(ValidationError, match="ATLAS_MCP_TOKEN"):
        Settings(_env_file=None)


def test_a_rejected_mcp_token_is_not_echoed_in_the_error(monkeypatch: pytest.MonkeyPatch) -> None:
    secret = "my-secret-token-1"
    monkeypatch.setenv("ATLAS_MCP_TOKEN", secret)

    with pytest.raises(ValidationError) as excinfo:
        Settings(_env_file=None)

    assert secret not in str(excinfo.value)
