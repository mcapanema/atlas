"""Terminal entry point: `python -m app.cli reset-password <email>` (`make reset-password`).

The way back in when the only admin forgets their password (ADR-0027). A
second composition root beside `app/api/deps.py`: it wires the concrete
adapters itself. The new password is read with getpass, never from argv or
the environment, so it stays out of shell history and process lists.
"""

import argparse
import asyncio
import getpass
import sys
from collections.abc import Callable

from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncEngine

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


async def _reset(email: str, password: str) -> None:
    settings = get_settings()
    sessionmaker = build_sessionmaker(
        settings.database_url, journal_mode=settings.sqlite_journal_mode
    )
    try:
        async with sessionmaker() as session:
            users = SqlAlchemyUserRepository(session)
            user = await users.get_by_email(email)
            if user is None:
                raise _CliError(f"No user with email {email}")
            await UserService(users, SqlAlchemyAuthSessionRepository(session)).reset_password(
                user.id, password
            )
            await session.commit()
    except OperationalError as exc:
        raise _CliError("Can't read the users table — run make migrate first.") from exc
    finally:
        engine = sessionmaker.kw["bind"]
        assert isinstance(engine, AsyncEngine)  # noqa: S101 — narrow Any for mypy; always true
        await engine.dispose()


def _reset_password(email: str, read_password: Callable[[str], str]) -> None:
    try:
        email = normalize_email(email)
        password = read_password("New password: ")
        if read_password("Repeat new password: ") != password:
            raise _CliError("The passwords don't match")
        require_valid_password(password)
    except ValueError as exc:
        raise _CliError(str(exc)) from exc
    asyncio.run(_reset(email, password))
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
    return 0


if __name__ == "__main__":
    sys.exit(main())
