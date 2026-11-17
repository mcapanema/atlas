import logging
from collections.abc import Callable
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config import Settings
from app.infrastructure.ai.advisor import DEFAULT_MAX_TOKENS, DEFAULT_TIMEOUT_SECONDS
from app.main import create_app

# Scrubbed from the real environment so a developer's shell or CI can't
# leak into assertions.
_VARS = (
    "ATLAS_DATABASE_URL",
    "ATLAS_DB_ECHO",
    "ATLAS_SQLITE_JOURNAL_MODE",
    "ATLAS_ADVISOR_SELF_CRITIQUE",
    "ATLAS_MCP_TOKEN",
    "ATLAS_SECRET_KEY_FILE",
    "ATLAS_ADVISOR_MAX_TOKENS",
    "ATLAS_ADVISOR_TIMEOUT_SECONDS",
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in _VARS:
        monkeypatch.delenv(var, raising=False)


def test_defaults_apply_without_env() -> None:
    settings = Settings(_env_file=None)

    assert settings.database_url == "sqlite+aiosqlite:///./data/atlas.db"
    assert settings.db_echo is False
    assert settings.advisor_self_critique is False


def test_secret_key_file_defaults_to_data_dir() -> None:
    assert Settings(_env_file=None).secret_key_file == Path("data/atlas.key")


def test_prefixed_env_var_overrides_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ATLAS_DB_ECHO", "true")

    assert Settings(_env_file=None).db_echo is True


def test_sqlite_journal_mode_defaults_to_wal() -> None:
    assert Settings(_env_file=None).sqlite_journal_mode == "wal"


def test_sqlite_journal_mode_reads_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ATLAS_SQLITE_JOURNAL_MODE", "delete")

    assert Settings(_env_file=None).sqlite_journal_mode == "delete"


@pytest.mark.parametrize("value", ["memory", "WAL", "delete; DROP TABLE teams"])
def test_sqlite_journal_mode_rejects_unsupported_values(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("ATLAS_SQLITE_JOURNAL_MODE", value)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_unprefixed_env_var_is_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DB_ECHO", "true")

    assert Settings(_env_file=None).db_echo is False


def test_env_file_is_read(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("ATLAS_ADVISOR_SELF_CRITIQUE=true\n")

    assert Settings(_env_file=env_file).advisor_self_critique is True


def test_real_env_var_beats_env_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # The documented contract (Settings docstring, app/config.py): real env vars always win
    # over .env.
    env_file = tmp_path / ".env"
    env_file.write_text("ATLAS_DB_ECHO=true\n")
    monkeypatch.setenv("ATLAS_DB_ECHO", "false")

    assert Settings(_env_file=env_file).db_echo is False


def test_a_leftover_mcp_token_env_var_logs_a_warning(
    settings_env: Callable[..., None], caplog: pytest.LogCaptureFixture
) -> None:
    settings_env(mcp_token="test-token-0123456789abcdefghij")

    with caplog.at_level(logging.WARNING, logger="app.main"):
        create_app()

    warnings = [
        r.getMessage()
        for r in caplog.records
        if r.name == "app.main" and r.levelno == logging.WARNING
    ]
    assert len([w for w in warnings if "AI access" in w]) == 1


def test_advisor_bounds_default_to_the_adapters() -> None:
    settings = Settings(_env_file=None)

    assert settings.advisor_max_tokens == DEFAULT_MAX_TOKENS
    assert settings.advisor_timeout_seconds == DEFAULT_TIMEOUT_SECONDS


def test_advisor_max_tokens_rejects_a_tiny_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ATLAS_ADVISOR_MAX_TOKENS", "10")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)
