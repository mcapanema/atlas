from pathlib import Path

import pytest

from app.config import Settings

# Scrubbed from the real environment so a developer's shell or CI can't
# leak into assertions.
_VARS = ("ATLAS_DATABASE_URL", "ATLAS_DB_ECHO", "ATLAS_ADVISOR_MODEL")


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


def test_real_env_var_beats_env_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The documented contract (root CLAUDE.md): real env vars always win
    # over .env. tests/api/test_connectors.py's hermeticity relies on it.
    env_file = tmp_path / ".env"
    env_file.write_text("ATLAS_ADVISOR_MODEL=model-from-dotenv\n")
    monkeypatch.setenv("ATLAS_ADVISOR_MODEL", "model-from-env")

    assert Settings(_env_file=env_file).advisor_model == "model-from-env"
