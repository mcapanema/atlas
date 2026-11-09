"""Terminal entry point: `python -m app.cli reset-password <email>` (`make reset-password`).

The way back in when the only admin forgets their password (ADR-0028). A
second composition root beside `app/api/deps.py`: it wires the concrete
adapters itself. The new password is read with getpass, never from argv or
the environment, so it stays out of shell history and process lists.
"""

import argparse
import asyncio
import getpass
import sqlite3
import sys
import threading
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager, suppress
from uuid import UUID

from sqlalchemy import inspect
from sqlalchemy.exc import ArgumentError, DBAPIError, InvalidRequestError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.orm import Session

from app.application.auth.service import UnknownUserError
from app.application.auth.users import UserService
from app.config import get_settings
from app.domain.auth.entities import normalize_email, require_valid_password
from app.infrastructure.database.session import build_sessionmaker
from app.infrastructure.repositories.auth import (
    SqlAlchemyAuthSessionRepository,
    SqlAlchemyUserRepository,
)


class _CliError(Exception):
    """A failure to report as one line on stderr, exit code 1."""


def _reason(error: BaseException) -> str:
    """The first non-blank line of the error's text, or its class name."""
    lines = (line.strip() for line in str(error).splitlines())
    return next((line for line in lines if line), type(error).__name__)


async def _join_sqlite_workers() -> None:
    """Wait for aiosqlite's worker threads to exit while the event loop is open.

    On a failed connect, aiosqlite (0.22.1) queues its worker's stop without
    awaiting it. asyncio.run can then close the loop before the worker reports
    back, and the worker raises "Event loop is closed" in its thread. After a
    clean run, dispose() has already stopped every worker, so this returns at once.
    """
    workers = [
        thread
        for thread in threading.enumerate()
        if thread.name.endswith("(_connection_worker_thread)")
    ]
    for worker in workers:
        await asyncio.to_thread(worker.join, 1.0)


def _has_users_table(session: Session) -> bool:
    return inspect(session.connection()).has_table("users")


@asynccontextmanager
async def _database() -> AsyncIterator[AsyncSession]:
    """One session on the configured database; the engine is disposed afterwards."""
    settings = get_settings()
    try:
        sessionmaker = build_sessionmaker(
            settings.database_url, journal_mode=settings.sqlite_journal_mode
        )
    except (ArgumentError, InvalidRequestError, ValueError):
        # A bad URL, port or sync driver. The text can hold the password: never
        # show or chain it.
        raise _CliError(
            "Can't use the database: ATLAS_DATABASE_URL is not a usable database URL."
        ) from None
    except ImportError as exc:  # the URL names a driver that isn't installed
        raise _CliError(f"Can't use the database: {_reason(exc)}") from exc
    except sqlite3.OperationalError as exc:  # the journal-mode switch: unopenable or locked
        raise _CliError(f"Can't use the database: {_reason(exc)}") from exc
    try:
        async with sessionmaker() as session:
            # inspect() works on every engine; SQLite and Postgres raise
            # different exception classes for a missing table.
            if not await session.run_sync(_has_users_table):
                raise _CliError("Can't read the users table — run make migrate first.")
            yield session
    except DBAPIError as exc:
        raise _CliError(f"Can't use the database: {_reason(exc.orig or exc)}") from exc
    except OSError as exc:  # asyncpg raises a raw OSError when it can't connect
        raise _CliError(f"Can't use the database: {_reason(exc)}") from exc
    finally:
        engine = sessionmaker.kw["bind"]
        assert isinstance(engine, AsyncEngine)  # noqa: S101 — narrow Any for mypy; always true
        # The outcome (success or a _CliError) is already decided; a failed
        # cleanup must not replace it.
        with suppress(DBAPIError, OSError):
            await engine.dispose()
        await _join_sqlite_workers()


async def _find_user(email: str) -> UUID:
    async with _database() as session:
        user = await SqlAlchemyUserRepository(session).get_by_email(email)
    if user is None:
        raise _CliError(f"No user with email {email}")
    return user.id


async def _reset(user_id: UUID, email: str, password: str) -> None:
    async with _database() as session:
        users = UserService(
            SqlAlchemyUserRepository(session), SqlAlchemyAuthSessionRepository(session)
        )
        try:
            await users.reset_password(user_id, password)
        except UnknownUserError as exc:  # removed while the prompts waited
            raise _CliError(f"No user with email {email}") from exc
        await session.commit()


def _read_new_password(read_password: Callable[[str], str]) -> str:
    password = read_password("New password: ")
    if read_password("Repeat new password: ") != password:
        raise _CliError("The passwords don't match")
    return password


def _reset_password(email: str, read_password: Callable[[str], str]) -> None:
    try:
        email = normalize_email(email)
    except ValueError as exc:
        raise _CliError(str(exc)) from exc
    # Look the user up first, so a typo fails before anyone types a password.
    user_id = asyncio.run(_find_user(email))
    password = _read_new_password(read_password)
    try:
        require_valid_password(password)
    except ValueError as exc:
        raise _CliError(str(exc)) from exc
    asyncio.run(_reset(user_id, email, password))
    sys.stdout.write(f"Password reset for {email}. Their sessions ended.\n")


def main(
    argv: list[str] | None = None, read_password: Callable[[str], str] = getpass.getpass
) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    reset = commands.add_parser("reset-password", help="set a new password for a user")
    reset.add_argument("email")
    args = parser.parse_args(argv)
    try:
        _reset_password(args.email, read_password)
    except _CliError as exc:
        sys.stderr.write(f"{exc}\n")
        return 1
    except (KeyboardInterrupt, EOFError):
        # An interrupt inside asyncio.run cancels the task, so the open
        # transaction rolls back; only the instant between the commit and the
        # success line could make "nothing changed" untrue.
        sys.stderr.write("\nCancelled; nothing changed.\n")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
