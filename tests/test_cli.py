"""`python -m app.cli reset-password` — the terminal way back in (ADR-0028)."""

import asyncio
import threading
import time
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path
from uuid import UUID

import aiosqlite
import aiosqlite.core
import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

import app.infrastructure.repositories  # noqa: F401  # registers ORM models on Base.metadata
from app.cli import _reason, main
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


async def _remove_ana(url: str) -> None:
    engine = create_async_engine(url)
    async with async_sessionmaker(engine)() as session:
        await session.execute(delete(AuthSessionModel))
        await session.execute(delete(UserModel))
        await session.commit()
    await engine.dispose()


def _no_prompt(prompt: str) -> str:
    raise AssertionError(f"prompted for {prompt!r}")


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
    code = main(["reset-password", "nobody@acme.com"], read_password=_no_prompt)

    assert code == 1
    assert capsys.readouterr().err == "No user with email nobody@acme.com\n"


def test_user_removed_while_prompting_exits_1(db: str, capsys: pytest.CaptureFixture[str]) -> None:
    def remove_ana_then_answer(prompt: str) -> str:
        asyncio.run(_remove_ana(db))
        return NEW_PASSWORD

    code = main(["reset-password", "ana@acme.com"], read_password=remove_ana_then_answer)

    assert code == 1
    assert capsys.readouterr().err == "No user with email ana@acme.com\n"


@pytest.mark.parametrize("error", [KeyboardInterrupt, EOFError])
@pytest.mark.parametrize("at_prompt", [1, 2])
def test_ctrl_c_at_a_prompt_cancels(
    db: str, capsys: pytest.CaptureFixture[str], error: type[BaseException], at_prompt: int
) -> None:
    answers = [NEW_PASSWORD] * (at_prompt - 1)

    def reader(prompt: str) -> str:
        if not answers:
            raise error
        return answers.pop()

    code = main(["reset-password", "ana@acme.com"], read_password=reader)

    assert code == 1
    assert capsys.readouterr().err == "\nCancelled; nothing changed.\n"
    assert asyncio.run(_stored(db))[0] == PASSWORD_HASH


def test_unmigrated_database_is_a_clear_error(
    tmp_path: Path, settings_env: Callable[..., None], capsys: pytest.CaptureFixture[str]
) -> None:
    settings_env(database_url=f"sqlite+aiosqlite:///{tmp_path / 'empty.db'}")

    code = main(["reset-password", "ana@acme.com"], read_password=_no_prompt)

    assert code == 1
    assert capsys.readouterr().err == "Can't read the users table — run make migrate first.\n"


def test_ctrl_c_during_the_lookup_cancels(
    db: str, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    async def interrupted(email: str) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr("app.cli._find_user", interrupted)

    code = main(
        ["reset-password", "ana@acme.com"], read_password=_reader(NEW_PASSWORD, NEW_PASSWORD)
    )

    assert code == 1
    assert capsys.readouterr().err == "\nCancelled; nothing changed.\n"


def test_ctrl_c_inside_the_write_keeps_the_old_password(
    db: str, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    real_delete = SqlAlchemyAuthSessionRepository.delete_for_user

    async def delete_then_interrupt(
        self: SqlAlchemyAuthSessionRepository, user_id: UUID, **kwargs: str | None
    ) -> None:
        await real_delete(self, user_id, **kwargs)  # the new hash is written, not committed
        raise KeyboardInterrupt

    monkeypatch.setattr(SqlAlchemyAuthSessionRepository, "delete_for_user", delete_then_interrupt)

    code = main(
        ["reset-password", "ana@acme.com"], read_password=_reader(NEW_PASSWORD, NEW_PASSWORD)
    )

    assert code == 1
    assert capsys.readouterr().err == "\nCancelled; nothing changed.\n"
    assert asyncio.run(_stored(db))[0] == PASSWORD_HASH


def test_unopenable_database_is_a_clear_error(
    tmp_path: Path, settings_env: Callable[..., None], capsys: pytest.CaptureFixture[str]
) -> None:
    settings_env(database_url=f"sqlite+aiosqlite:///{tmp_path / 'no-such-dir' / 'atlas.db'}")

    code = main(["reset-password", "ana@acme.com"], read_password=_no_prompt)

    err = capsys.readouterr().err
    assert code == 1
    assert err.startswith("Can't use the database: ")
    assert "migrate" not in err
    assert str(tmp_path) not in err


def _aiosqlite_workers() -> list[threading.Thread]:
    return [t for t in threading.enumerate() if t.name.endswith("(_connection_worker_thread)")]


def test_a_failed_connect_leaves_no_worker_error_behind(
    tmp_path: Path,
    settings_env: Callable[..., None],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # On a failed connect aiosqlite queues its worker's stop without awaiting it.
    # A 50 ms queue item ahead of the stop plays a slow runner: unless the CLI
    # waits, asyncio.run closes the loop first and the worker raises "Event loop
    # is closed" in its thread (the flaky CI error).
    stop = aiosqlite.core.Connection.stop

    def slow_stop(self: aiosqlite.Connection) -> asyncio.Future[object] | None:
        self._tx.put_nowait((None, lambda: time.sleep(0.05)))
        return stop(self)

    errors: list[BaseException | None] = []
    monkeypatch.setattr(aiosqlite.core.Connection, "stop", slow_stop)
    monkeypatch.setattr(threading, "excepthook", lambda args: errors.append(args.exc_value))
    settings_env(database_url=f"sqlite+aiosqlite:///{tmp_path / 'no-such-dir' / 'atlas.db'}")

    assert main(["reset-password", "ana@acme.com"], read_password=_no_prompt) == 1
    capsys.readouterr()

    for worker in _aiosqlite_workers():
        worker.join(timeout=2)
    assert errors == []


def test_reason_skips_blank_lines() -> None:
    assert _reason(Exception("\n  \nreal reason\nmore")) == "real reason"
    assert _reason(ValueError("")) == "ValueError"


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+nosuchdriver://atlas:s3cret@db/atlas",  # unknown dialect
        "not a url :s3cret@",  # can't be parsed
        "postgresql+asyncpg://atlas:s3cret@db:notaport/atlas",  # bad port
        "sqlite:///./data/s3cret.db",  # a sync driver
    ],
)
def test_unusable_url_is_a_clear_error(
    settings_env: Callable[..., None], capsys: pytest.CaptureFixture[str], url: str
) -> None:
    settings_env(database_url=url)

    code = main(["reset-password", "ana@acme.com"], read_password=_no_prompt)

    err = capsys.readouterr().err
    assert code == 1
    assert err == "Can't use the database: ATLAS_DATABASE_URL is not a usable database URL.\n"


def test_missing_driver_is_a_clear_error(
    settings_env: Callable[..., None], capsys: pytest.CaptureFixture[str]
) -> None:
    settings_env(database_url="postgresql+asyncpg://atlas:s3cret@127.0.0.1:1/atlas")

    code = main(["reset-password", "ana@acme.com"], read_password=_no_prompt)

    err = capsys.readouterr().err
    assert code == 1
    assert err.startswith("Can't use the database: ")
    assert "s3cret" not in err


def test_refused_connection_is_a_clear_error(
    db: str, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def refused(session: object) -> bool:
        raise ConnectionRefusedError(61, "Connect call failed")

    monkeypatch.setattr("app.cli._has_users_table", refused)

    code = main(["reset-password", "ana@acme.com"], read_password=_no_prompt)

    assert code == 1
    assert capsys.readouterr().err == "Can't use the database: [Errno 61] Connect call failed\n"


@pytest.mark.parametrize(
    ("email", "code", "err"),
    [("nobody@acme.com", 1, "No user with email nobody@acme.com\n"), ("ana@acme.com", 0, "")],
)
def test_dispose_failure_never_hides_the_outcome(
    db: str,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    email: str,
    code: int,
    err: str,
) -> None:
    real_dispose = AsyncEngine.dispose

    async def broken_dispose(self: AsyncEngine, close: bool = True) -> None:
        await real_dispose(self, close)  # close the pool, or a ResourceWarning fails the run
        raise OSError("disk went away")

    with monkeypatch.context() as patched:  # _stored and _seed must dispose normally
        patched.setattr(AsyncEngine, "dispose", broken_dispose)
        result = main(["reset-password", email], read_password=_reader(NEW_PASSWORD, NEW_PASSWORD))

    assert (result, capsys.readouterr().err) == (code, err)


def test_password_never_comes_from_argv() -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["reset-password", "a@b.co", "--password", "x"])

    assert exit_info.value.code == 2
