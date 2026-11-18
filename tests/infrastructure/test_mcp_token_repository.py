from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.auth.entities import McpAccess, McpToken, User
from app.infrastructure.repositories.auth import (
    SqlAlchemyMcpTokenRepository,
    SqlAlchemyUserRepository,
)

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


async def _user(session: AsyncSession, email: str = "ana@acme.com") -> User:
    user = User(email=email, name="Ana", password_hash=None)
    await SqlAlchemyUserRepository(session).add(user)
    return user


def _token(
    user: User,
    digest: str,
    created_at: datetime = _NOW,
    last_used_at: datetime | None = None,
) -> McpToken:
    return McpToken(
        user.id,
        "Claude Code",
        McpAccess.READ_WRITE,
        digest,
        "abcd",
        created_at=created_at,
        last_used_at=last_used_at,
    )


async def test_add_then_get_by_hash_round_trips(session: AsyncSession) -> None:
    user = await _user(session)
    repo = SqlAlchemyMcpTokenRepository(session)
    token = _token(user, "a" * 64, last_used_at=_NOW + timedelta(hours=1))

    await repo.add(token)

    assert await repo.get_by_hash("a" * 64) == token
    assert await repo.get_by_hash("b" * 64) is None


async def test_list_for_user_returns_only_that_users_tokens_newest_first(
    session: AsyncSession,
) -> None:
    ana = await _user(session)
    bob = await _user(session, "bob@acme.com")
    repo = SqlAlchemyMcpTokenRepository(session)
    old = _token(ana, "a" * 64)
    new = _token(ana, "b" * 64, created_at=_NOW + timedelta(days=1))
    await repo.add(old)
    await repo.add(new)
    await repo.add(_token(bob, "c" * 64))

    assert await repo.list_for_user(ana.id) == [new, old]


async def test_delete_refuses_another_users_token(session: AsyncSession) -> None:
    ana = await _user(session)
    bob = await _user(session, "bob@acme.com")
    repo = SqlAlchemyMcpTokenRepository(session)
    token = _token(ana, "a" * 64)
    await repo.add(token)

    assert await repo.delete(token.id, bob.id) is False
    assert await repo.get_by_hash("a" * 64) == token
    assert await repo.delete(token.id, ana.id) is True
    assert await repo.get_by_hash("a" * 64) is None


async def test_touch_sets_last_used_at(session: AsyncSession) -> None:
    user = await _user(session)
    repo = SqlAlchemyMcpTokenRepository(session)
    token = _token(user, "a" * 64)
    await repo.add(token)

    await repo.touch(token.id, _NOW)

    stored = await repo.get_by_hash("a" * 64)
    assert stored is not None
    assert stored.last_used_at == _NOW


async def test_deleting_the_user_deletes_their_tokens(session: AsyncSession) -> None:
    user = await _user(session)
    repo = SqlAlchemyMcpTokenRepository(session)
    await repo.add(_token(user, "a" * 64))

    await SqlAlchemyUserRepository(session).delete(user.id)

    assert await repo.get_by_hash("a" * 64) is None
