import asyncio
from datetime import datetime, timedelta

import pytest

from app.application.auth.service import (
    AuthService,
    InvalidCredentialsError,
    SetupClosedError,
    TooManySignInsError,
)
from app.domain._time import utcnow
from app.domain.auth.entities import SESSION_LIFETIME, AuthSession, User
from app.domain.auth.passwords import hash_password
from app.domain.auth.repository import SetupAlreadyClaimedError
from app.domain.auth.throttle import SignInThrottle
from app.domain.auth.tokens import hash_token
from tests.fakes import InMemoryAuthSessionRepository, InMemoryUserRepository

PASSWORD = "correct horse battery"
NOW = utcnow()


def make_service(
    now: datetime = NOW,
) -> tuple[AuthService, InMemoryUserRepository, InMemoryAuthSessionRepository]:
    users = InMemoryUserRepository()
    sessions = InMemoryAuthSessionRepository()
    return AuthService(users, sessions, SignInThrottle(), now=lambda: now), users, sessions


async def test_setup_creates_an_admin_and_a_session() -> None:
    service, _, _ = make_service()
    assert await service.setup_required()

    signed_in = await service.create_first_admin("ana@acme.com", "Ana", PASSWORD)

    assert signed_in.user.is_admin
    assert await service.user_for_token(signed_in.token) == signed_in.user
    assert not await service.setup_required()


async def test_setup_is_refused_once_a_user_exists() -> None:
    service, _, _ = make_service()
    await service.create_first_admin("ana@acme.com", "Ana", PASSWORD)

    with pytest.raises(SetupClosedError):
        await service.create_first_admin("bo@acme.com", "Bo", PASSWORD)


async def test_sign_in_normalizes_email() -> None:
    service, _, _ = make_service()
    await service.create_first_admin("ana@acme.com", "Ana", PASSWORD)

    signed_in = await service.sign_in(" ANA@acme.com", PASSWORD)

    assert signed_in.user.email == "ana@acme.com"


async def test_wrong_password_and_unknown_email_fail_the_same_way() -> None:
    service, _, _ = make_service()
    await service.create_first_admin("ana@acme.com", "Ana", PASSWORD)

    with pytest.raises(InvalidCredentialsError) as wrong:
        await service.sign_in("ana@acme.com", "not the password")
    with pytest.raises(InvalidCredentialsError) as unknown:
        await service.sign_in("nobody@acme.com", PASSWORD)

    assert str(wrong.value) == str(unknown.value) == "Wrong email or password"


async def test_user_without_a_password_cannot_sign_in() -> None:
    service, users, _ = make_service()
    await users.add(User(email="sso@acme.com", name="Sso", password_hash=None))

    with pytest.raises(InvalidCredentialsError):
        await service.sign_in("sso@acme.com", PASSWORD)


async def test_expired_session_is_rejected_and_deleted() -> None:
    service, users, sessions = make_service()
    signed_in = await service.create_first_admin("ana@acme.com", "Ana", PASSWORD)
    later = AuthService(
        users, sessions, SignInThrottle(), now=lambda: NOW + SESSION_LIFETIME + timedelta(seconds=1)
    )

    assert await later.user_for_token(signed_in.token) is None
    assert await sessions.get(hash_token(signed_in.token)) is None


async def test_unknown_token_is_none() -> None:
    service, _, _ = make_service()
    assert await service.user_for_token("nope") is None


async def test_sign_out_ends_the_session() -> None:
    service, _, _ = make_service()
    signed_in = await service.create_first_admin("ana@acme.com", "Ana", PASSWORD)

    await service.sign_out(signed_in.token)

    assert await service.user_for_token(signed_in.token) is None


async def test_change_password_keeps_this_session_and_ends_the_others() -> None:
    service, _, _ = make_service()
    first = await service.create_first_admin("ana@acme.com", "Ana", PASSWORD)
    other = await service.sign_in("ana@acme.com", PASSWORD)
    new = "a brand new password"

    await service.change_password(first.user, PASSWORD, new, keep_token=first.token)

    assert await service.user_for_token(first.token) is not None
    assert await service.user_for_token(other.token) is None
    await service.sign_in("ana@acme.com", new)


async def test_change_password_needs_the_current_one() -> None:
    service, _, _ = make_service()
    first = await service.create_first_admin("ana@acme.com", "Ana", PASSWORD)

    with pytest.raises(InvalidCredentialsError):
        await service.change_password(first.user, "wrong", "a brand new password", first.token)


async def test_change_password_rejects_a_short_new_password() -> None:
    service, _, _ = make_service()
    first = await service.create_first_admin("ana@acme.com", "Ana", PASSWORD)

    with pytest.raises(ValueError, match="Password must be"):
        await service.change_password(first.user, PASSWORD, "short", first.token)


async def test_change_password_for_a_user_without_one_is_refused() -> None:
    service, users, _ = make_service()
    user = User(email="sso@acme.com", name="Sso", password_hash=hash_password(PASSWORD))
    user.password_hash = None
    await users.add(user)

    with pytest.raises(InvalidCredentialsError):
        await service.change_password(user, PASSWORD, "a brand new password", "t")


async def test_setup_refused_when_claim_is_taken() -> None:
    service, users, _ = make_service()
    await users.claim_setup(NOW)  # another transaction won the race

    with pytest.raises(SetupClosedError, match="sign in instead"):
        await service.create_first_admin("ana@acme.com", "Ana", PASSWORD)

    assert await users.count() == 0


async def test_setup_claims_before_adding_the_user() -> None:
    service, users, _ = make_service()

    await service.create_first_admin("ana@acme.com", "Ana", PASSWORD)

    with pytest.raises(SetupAlreadyClaimedError):
        await users.claim_setup(NOW)


async def test_sign_in_purges_expired_sessions() -> None:
    service, users, sessions = make_service()
    await service.create_first_admin("ana@acme.com", "Ana", PASSWORD)
    other = User(email="bo@acme.com", name="Bo", password_hash=None)
    await users.add(other)
    await sessions.add(AuthSession("stale", other.id, expires_at=NOW - timedelta(minutes=1)))
    await sessions.add(AuthSession("live", other.id, expires_at=NOW + timedelta(minutes=1)))

    await service.sign_in("ana@acme.com", PASSWORD)

    assert await sessions.get("stale") is None
    assert await sessions.get("live") is not None


async def _fail_sign_ins(service: AuthService, email: str, times: int = 5) -> None:
    for _ in range(times):
        with pytest.raises(InvalidCredentialsError):
            await service.sign_in(email, "wrong password!")


async def test_key_ignores_case_and_spaces() -> None:
    service, _, _ = make_service()
    await service.create_first_admin("ana@acme.com", "Ana", PASSWORD)
    await _fail_sign_ins(service, " Ana@Acme.com ")

    with pytest.raises(TooManySignInsError) as locked:
        await service.sign_in("ana@acme.com", PASSWORD)

    assert locked.value.retry_after == timedelta(minutes=15)


async def test_locked_sign_in_skips_password_check() -> None:
    service, _, _ = make_service()
    await service.create_first_admin("ana@acme.com", "Ana", PASSWORD)
    await _fail_sign_ins(service, "ana@acme.com")

    with pytest.raises(TooManySignInsError):
        await service.sign_in("ana@acme.com", PASSWORD)


async def test_unknown_email_is_throttled_too() -> None:
    service, _, _ = make_service()
    await _fail_sign_ins(service, "nobody@acme.com")

    with pytest.raises(TooManySignInsError):
        await service.sign_in("nobody@acme.com", PASSWORD)


async def test_successful_sign_in_clears_the_count() -> None:
    service, _, _ = make_service()
    await service.create_first_admin("ana@acme.com", "Ana", PASSWORD)
    await _fail_sign_ins(service, "ana@acme.com", times=4)
    await service.sign_in("ana@acme.com", PASSWORD)

    await _fail_sign_ins(service, "ana@acme.com", times=4)

    assert (await service.sign_in("ana@acme.com", PASSWORD)).user.email == "ana@acme.com"


async def test_a_burst_of_sign_ins_is_throttled_too() -> None:
    service, _, _ = make_service()
    await service.create_first_admin("ana@acme.com", "Ana", PASSWORD)

    outcomes = await asyncio.gather(
        *(service.sign_in("ana@acme.com", "wrong password!") for _ in range(20)),
        return_exceptions=True,
    )

    assert sum(isinstance(o, InvalidCredentialsError) for o in outcomes) == 5
    assert sum(isinstance(o, TooManySignInsError) for o in outcomes) == 15
