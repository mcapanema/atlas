from datetime import datetime, timedelta

import pytest

from app.application.auth.mcp_tokens import McpTokenService, UnknownMcpTokenError
from app.domain._time import utcnow
from app.domain.auth.entities import McpAccess, User
from app.domain.auth.tokens import hash_token
from tests.fakes import InMemoryMcpTokenRepository

NOW = utcnow()


def make_user(email: str = "ana@acme.com") -> User:
    return User(email=email, name="Ana", password_hash="x")


class Clock:
    def __init__(self) -> None:
        self.now: datetime = NOW

    def __call__(self) -> datetime:
        return self.now


def make_service() -> tuple[McpTokenService, InMemoryMcpTokenRepository, Clock]:
    repo = InMemoryMcpTokenRepository()
    clock = Clock()
    return McpTokenService(repo, now=clock), repo, clock


async def test_issue_returns_the_secret_once_and_stores_only_its_hash() -> None:
    service, repo, _ = make_service()
    user = make_user()

    issued = await service.issue(user, "Claude Code", McpAccess.READ_WRITE)

    stored = await repo.get_by_hash(hash_token(issued.secret))
    assert stored == issued.token
    assert stored is not None
    assert stored.token_hash == hash_token(issued.secret)
    assert stored.hint == issued.secret[-4:]
    assert issued.secret not in repr(stored)
    assert await service.list(user) == [issued.token]


async def test_authenticate_returns_the_access_of_a_known_token() -> None:
    service, _, _ = make_service()
    issued = await service.issue(make_user(), "ro", McpAccess.READ)

    assert await service.authenticate(issued.secret) == McpAccess.READ


async def test_authenticate_returns_none_for_an_unknown_secret() -> None:
    service, _, _ = make_service()

    assert await service.authenticate("atlas_mcp_nope") is None


async def test_authenticate_touches_last_used_at_at_most_once_per_resolution() -> None:
    service, repo, clock = make_service()
    issued = await service.issue(make_user(), "ro", McpAccess.READ)

    await service.authenticate(issued.secret)
    clock.now = NOW + timedelta(minutes=1)
    await service.authenticate(issued.secret)
    assert len(repo.touches) == 1

    clock.now = NOW + timedelta(minutes=6)
    await service.authenticate(issued.secret)
    assert [when for _, when in repo.touches] == [NOW, NOW + timedelta(minutes=6)]


async def test_revoke_deletes_the_token() -> None:
    service, _, _ = make_service()
    user = make_user()
    issued = await service.issue(user, "ro", McpAccess.READ)

    await service.revoke(user, issued.token.id)

    assert await service.list(user) == []
    assert await service.authenticate(issued.secret) is None


async def test_revoke_refuses_another_users_token() -> None:
    service, _, _ = make_service()
    issued = await service.issue(make_user(), "ro", McpAccess.READ)

    with pytest.raises(UnknownMcpTokenError):
        await service.revoke(make_user("bob@acme.com"), issued.token.id)
