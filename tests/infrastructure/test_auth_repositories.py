from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.auth.entities import AuthSession, User
from app.domain.auth.repository import SetupAlreadyClaimedError
from app.infrastructure.repositories.auth import (
    AuthSetupModel,
    SqlAlchemyAuthSessionRepository,
    SqlAlchemyUserRepository,
)

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _session(token_hash: str, user: User) -> AuthSession:
    return AuthSession(token_hash=token_hash, user_id=user.id, expires_at=_NOW + timedelta(days=14))


async def test_user_round_trips(session: AsyncSession) -> None:
    repo = SqlAlchemyUserRepository(session)
    user = User(email="ana@acme.com", name="Ana", password_hash=None, created_at=_NOW)

    await repo.add(user)

    assert await repo.get(user.id) == user
    assert await repo.get_by_email("ana@acme.com") == user
    assert await repo.get_by_email("nobody@acme.com") is None


async def test_duplicate_email_raises_integrity_error(session: AsyncSession) -> None:
    repo = SqlAlchemyUserRepository(session)
    await repo.add(User(email="ana@acme.com", name="Ana", password_hash=None))

    with pytest.raises(IntegrityError):
        await repo.add(User(email="ana@acme.com", name="Other", password_hash=None))


async def test_list_is_ordered_by_creation_and_count_matches(session: AsyncSession) -> None:
    repo = SqlAlchemyUserRepository(session)
    later = User(email="b@acme.com", name="B", password_hash=None, created_at=_NOW + timedelta(1))
    earlier = User(email="a@acme.com", name="A", password_hash=None, created_at=_NOW)
    await repo.add(later)
    await repo.add(earlier)

    assert [u.email for u in await repo.list()] == ["a@acme.com", "b@acme.com"]
    assert await repo.count() == 2


async def test_update_changes_password_hash(session: AsyncSession) -> None:
    repo = SqlAlchemyUserRepository(session)
    user = User(email="ana@acme.com", name="Ana", password_hash="old")
    await repo.add(user)

    user.password_hash = "new"
    user.name = "Ana B"
    user.is_admin = True
    await repo.update(user)

    assert await repo.get(user.id) == user


async def test_deleting_a_user_deletes_their_sessions(session: AsyncSession) -> None:
    users = SqlAlchemyUserRepository(session)
    sessions = SqlAlchemyAuthSessionRepository(session)
    user = User(email="ana@acme.com", name="Ana", password_hash=None)
    await users.add(user)
    await sessions.add(_session("a", user))
    await sessions.add(_session("b", user))

    await users.delete(user.id)

    assert await sessions.get("a") is None
    assert await sessions.get("b") is None


async def test_session_round_trips_and_deletes(session: AsyncSession) -> None:
    users = SqlAlchemyUserRepository(session)
    sessions = SqlAlchemyAuthSessionRepository(session)
    user = User(email="ana@acme.com", name="Ana", password_hash=None)
    await users.add(user)
    stored = _session("a", user)
    await sessions.add(stored)

    assert await sessions.get("a") == stored

    await sessions.delete("a")

    assert await sessions.get("a") is None


async def test_delete_for_user_can_keep_one_session(session: AsyncSession) -> None:
    users = SqlAlchemyUserRepository(session)
    sessions = SqlAlchemyAuthSessionRepository(session)
    user = User(email="ana@acme.com", name="Ana", password_hash=None)
    other = User(email="bo@acme.com", name="Bo", password_hash=None)
    await users.add(user)
    await users.add(other)
    for token in ("a", "b", "c"):
        await sessions.add(_session(token, user))
    await sessions.add(_session("z", other))

    await sessions.delete_for_user(user.id, keep_token_hash="b")

    assert [await sessions.get(t) is not None for t in ("a", "b", "c", "z")] == [
        False,
        True,
        False,
        True,
    ]

    await sessions.delete_for_user(user.id)

    assert await sessions.get("b") is None


async def test_second_claim_is_refused(
    file_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    async with file_sessionmaker() as first:
        await SqlAlchemyUserRepository(first).claim_setup(_NOW)
        await first.commit()

    async with file_sessionmaker() as second:
        with pytest.raises(SetupAlreadyClaimedError):
            await SqlAlchemyUserRepository(second).claim_setup(_NOW)
        await second.rollback()
        rows = await second.execute(select(func.count()).select_from(AuthSetupModel))
        assert rows.scalar_one() == 1


async def test_failed_claim_leaves_the_session_usable(session: AsyncSession) -> None:
    repo = SqlAlchemyUserRepository(session)
    await repo.claim_setup(_NOW)

    with pytest.raises(SetupAlreadyClaimedError):
        await repo.claim_setup(_NOW)

    assert await repo.count() == 0
