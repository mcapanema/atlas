"""`python -m app.cli reset-password` — the terminal way back in (ADR-0027)."""

import asyncio
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.infrastructure.repositories  # noqa: F401  # registers ORM models on Base.metadata
from app.cli import main
from app.domain._time import utcnow
from app.domain.auth.entities import AuthSession, User
from app.domain.auth.passwords import verify_password
from app.infrastructure.database.base import Base
from app.infrastructure.repositories.auth import (
    AuthSessionModel,
    SqlAlchemyAuthSessionRepository,
    SqlAlchemyUserRepository,
    UserModel,
)
from tests.conftest import PASSWORD_HASH

NEW_PASSWORD = "a-brand-new-passphrase"


def _reader(*answers: str) -> Callable[[str], str]:
    queue = list(answers)
    return lambda prompt: queue.pop(0)


async def _seed(url: str) -> None:
    engine = create_async_engine(url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(engine)() as session:
        user = User(email="ana@acme.com", name="Ana", password_hash=PASSWORD_HASH)
        await SqlAlchemyUserRepository(session).add(user)
        await SqlAlchemyAuthSessionRepository(session).add(
            AuthSession("old-session", user.id, expires_at=utcnow() + timedelta(days=1))
        )
        await session.commit()
    await engine.dispose()


async def _stored(url: str) -> tuple[str | None, int]:
    """Ana's password hash and how many sessions are left."""
    engine = create_async_engine(url)
    async with async_sessionmaker(engine)() as session:
        stored = (await session.execute(select(UserModel.password_hash))).scalar_one()
        sessions = len((await session.execute(select(AuthSessionModel))).all())
    await engine.dispose()
    return stored, sessions


@pytest.fixture
def db(tmp_path: Path, settings_env: Callable[..., None]) -> str:
    url = f"sqlite+aiosqlite:///{tmp_path / 'atlas.db'}"
    asyncio.run(_seed(url))
    settings_env(database_url=url)
    return url


def test_reset_password_sets_the_new_password_and_ends_sessions(
    db: str, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(
        ["reset-password", "Ana@Acme.com"], read_password=_reader(NEW_PASSWORD, NEW_PASSWORD)
    )

    stored, sessions = asyncio.run(_stored(db))
    assert code == 0
    assert capsys.readouterr().out == "Password reset for ana@acme.com. Their sessions ended.\n"
    assert stored is not None
    assert verify_password(NEW_PASSWORD, stored)
    assert sessions == 0


def test_mismatch_exits_1(db: str, capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["reset-password", "ana@acme.com"], read_password=_reader(NEW_PASSWORD, "other"))

    assert code == 1
    assert capsys.readouterr().err == "The passwords don't match\n"
    assert asyncio.run(_stored(db))[0] == PASSWORD_HASH


def test_short_password_exits_1(db: str, capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["reset-password", "ana@acme.com"], read_password=_reader("short", "short"))

    assert code == 1
    assert "12" in capsys.readouterr().err
    assert asyncio.run(_stored(db))[0] == PASSWORD_HASH


def test_unknown_email_exits_1(db: str, capsys: pytest.CaptureFixture[str]) -> None:
    code = main(
        ["reset-password", "nobody@acme.com"], read_password=_reader(NEW_PASSWORD, NEW_PASSWORD)
    )

    assert code == 1
    assert capsys.readouterr().err == "No user with email nobody@acme.com\n"


def test_unmigrated_database_is_a_clear_error(
    tmp_path: Path, settings_env: Callable[..., None], capsys: pytest.CaptureFixture[str]
) -> None:
    settings_env(database_url=f"sqlite+aiosqlite:///{tmp_path / 'empty.db'}")

    code = main(
        ["reset-password", "ana@acme.com"], read_password=_reader(NEW_PASSWORD, NEW_PASSWORD)
    )

    assert code == 1
    assert capsys.readouterr().err == "Can't read the users table — run make migrate first.\n"


def test_password_never_comes_from_argv() -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["reset-password", "a@b.co", "--password", "x"])

    assert exit_info.value.code == 2
