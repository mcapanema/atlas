import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.domain._time import utcnow
from app.domain.auth.entities import (
    SESSION_LIFETIME,
    AuthSession,
    User,
    normalize_email,
    require_valid_password,
)
from app.domain.auth.passwords import hash_password, verify_password
from app.domain.auth.repository import (
    AuthSessionRepository,
    SetupAlreadyClaimedError,
    UserRepository,
)
from app.domain.auth.throttle import SignInThrottle
from app.domain.auth.tokens import hash_token, new_session_token


class InvalidCredentialsError(Exception):
    """The email or password is wrong. One message for both, so it reveals nothing."""


class TooManySignInsError(Exception):
    """This email failed to sign in too often; it stays locked for retry_after."""

    def __init__(self, retry_after: timedelta) -> None:
        super().__init__("Too many failed sign-ins")
        self.retry_after = retry_after


class SetupClosedError(Exception):
    """First-run setup was asked for, but an account already exists."""


class EmailTakenError(Exception):
    """Another user already has this email."""


class UnknownUserError(Exception):
    """The user does not exist."""


class SelfRemovalError(Exception):
    """An admin tried to remove their own account."""


@dataclass(frozen=True)
class SignedIn:
    user: User
    token: str


_dummy_hash: str | None = None


async def _dummy_password_hash() -> str:
    """A hash to verify against when the email is unknown, so timing does not leak it."""
    global _dummy_hash
    if _dummy_hash is None:
        _dummy_hash = await asyncio.to_thread(hash_password, "atlas-timing-equalizer")
    return _dummy_hash


class AuthService:
    """Application use cases for first-run setup, sign-in and sessions."""

    def __init__(
        self,
        users: UserRepository,
        sessions: AuthSessionRepository,
        throttle: SignInThrottle,
        now: Callable[[], datetime] = utcnow,
    ) -> None:
        self._users = users
        self._sessions = sessions
        self._throttle = throttle
        self._now = now

    async def setup_required(self) -> bool:
        return await self._users.count() == 0

    async def create_first_admin(self, email: str, name: str, password: str) -> SignedIn:
        closed = SetupClosedError("Atlas already has an account; sign in instead")
        if not await self.setup_required():
            raise closed
        require_valid_password(password)
        password_hash = await asyncio.to_thread(hash_password, password)
        user = User(email=email, name=name, password_hash=password_hash, is_admin=True)
        # Two simultaneous setups can both pass the count check; only one claim wins.
        try:
            await self._users.claim_setup(self._now())
        except SetupAlreadyClaimedError as exc:
            raise closed from exc
        await self._users.add(user)
        return await self._start_session(user)

    async def sign_in(self, email: str, password: str) -> SignedIn:
        try:
            key = normalize_email(email)
        except ValueError:
            key = None
        throttle_key = key or email.strip().lower()
        retry_after = self._throttle.retry_after(throttle_key)
        if retry_after is not None:
            raise TooManySignInsError(retry_after)
        # Count the attempt before the first await: a burst of parallel requests
        # would otherwise all pass the check above before any failure lands.
        self._throttle.record_failure(throttle_key)
        user = await self._users.get_by_email(key) if key is not None else None
        stored = user.password_hash if user is not None else None
        valid = await asyncio.to_thread(
            verify_password, password, stored or await _dummy_password_hash()
        )
        if user is None or stored is None or not valid:
            raise InvalidCredentialsError("Wrong email or password")
        self._throttle.clear(throttle_key)
        return await self._start_session(user)

    async def user_for_token(self, token: str) -> User | None:
        token_hash = hash_token(token)
        session = await self._sessions.get(token_hash)
        if session is None:
            return None
        if session.is_expired(self._now()):
            await self._sessions.delete(token_hash)
            return None
        return await self._users.get(session.user_id)

    async def sign_out(self, token: str) -> None:
        await self._sessions.delete(hash_token(token))

    async def change_password(self, user: User, current: str, new: str, keep_token: str) -> None:
        require_valid_password(new)
        stored = user.password_hash
        valid = stored is not None and await asyncio.to_thread(verify_password, current, stored)
        if not valid:
            raise InvalidCredentialsError("Wrong email or password")
        user.password_hash = await asyncio.to_thread(hash_password, new)
        await self._users.update(user)
        await self._sessions.delete_for_user(user.id, keep_token_hash=hash_token(keep_token))

    async def _start_session(self, user: User) -> SignedIn:
        # Every new session sweeps the expired ones, so abandoned rows never pile up.
        await self._sessions.delete_expired(self._now())
        token, token_hash = new_session_token()
        await self._sessions.add(
            AuthSession(token_hash, user.id, expires_at=self._now() + SESSION_LIFETIME)
        )
        return SignedIn(user=user, token=token)
