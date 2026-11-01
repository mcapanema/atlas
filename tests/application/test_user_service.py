from datetime import timedelta
from uuid import uuid4

import pytest

from app.application.auth.service import (
    EmailTakenError,
    SelfRemovalError,
    UnknownUserError,
)
from app.application.auth.users import UserService
from app.domain._time import utcnow
from app.domain.auth.entities import AuthSession, User
from app.domain.auth.passwords import verify_password
from app.domain.auth.throttle import SignInThrottle
from app.domain.auth.tokens import hash_token
from tests.fakes import InMemoryAuthSessionRepository, InMemoryUserRepository

PASSWORD = "correct horse battery"


def make_service() -> tuple[UserService, InMemoryUserRepository, InMemoryAuthSessionRepository]:
    users = InMemoryUserRepository()
    sessions = InMemoryAuthSessionRepository()
    return UserService(users, sessions), users, sessions


async def add_session(sessions: InMemoryAuthSessionRepository, user: User, token: str) -> None:
    now = utcnow()
    expires = now + timedelta(days=365)
    await sessions.add(AuthSession(hash_token(token), user.id, expires))


async def test_create_user_stores_a_hashed_password() -> None:
    service, users, _ = make_service()

    user = await service.create_user("Bo@acme.com", "Bo", PASSWORD, is_admin=False)

    assert user.email == "bo@acme.com"
    assert not user.is_admin
    assert user.password_hash is not None
    assert verify_password(PASSWORD, user.password_hash)
    assert await users.list() == [user]
    assert await service.list_users() == [user]


async def test_create_user_rejects_a_taken_email() -> None:
    service, _, _ = make_service()
    await service.create_user("bo@acme.com", "Bo", PASSWORD, is_admin=False)

    with pytest.raises(EmailTakenError, match=r"bo@acme\.com"):
        await service.create_user("BO@acme.com", "Other", PASSWORD, is_admin=True)


async def test_reset_password_ends_their_sessions() -> None:
    service, _, sessions = make_service()
    user = await service.create_user("bo@acme.com", "Bo", PASSWORD, is_admin=False)
    await add_session(sessions, user, "t1")

    await service.reset_password(user.id, "another long password")

    assert await sessions.get(hash_token("t1")) is None
    assert user.password_hash is not None
    assert verify_password("another long password", user.password_hash)


async def test_delete_user_ends_sessions_and_removes() -> None:
    service, users, sessions = make_service()
    admin = await service.create_user("ana@acme.com", "Ana", PASSWORD, is_admin=True)
    user = await service.create_user("bo@acme.com", "Bo", PASSWORD, is_admin=False)
    await add_session(sessions, user, "t1")

    await service.delete_user(admin, user.id)

    assert await users.get(user.id) is None
    assert await sessions.get(hash_token("t1")) is None


async def test_admin_cannot_remove_themselves() -> None:
    service, users, _ = make_service()
    admin = await service.create_user("ana@acme.com", "Ana", PASSWORD, is_admin=True)

    with pytest.raises(SelfRemovalError):
        await service.delete_user(admin, admin.id)

    assert await users.get(admin.id) is not None


async def test_unknown_id_on_reset_and_delete() -> None:
    service, _, _ = make_service()
    admin = await service.create_user("ana@acme.com", "Ana", PASSWORD, is_admin=True)
    missing = uuid4()

    with pytest.raises(UnknownUserError, match=str(missing)):
        await service.reset_password(missing, PASSWORD)
    with pytest.raises(UnknownUserError, match=str(missing)):
        await service.delete_user(admin, missing)


async def test_reset_password_lifts_the_sign_in_lock() -> None:
    users = InMemoryUserRepository()
    throttle = SignInThrottle()
    service = UserService(users, InMemoryAuthSessionRepository(), throttle)
    user = await service.create_user("ana@acme.com", "Ana", PASSWORD, is_admin=False)
    now = utcnow()
    for _ in range(5):
        throttle.record_failure("ana@acme.com", now)

    await service.reset_password(user.id, "a-brand-new-passphrase")

    assert throttle.retry_after("ana@acme.com", now) is None
