import asyncio
from uuid import UUID

from app.application.auth.service import (
    EmailTakenError,
    SelfRemovalError,
    UnknownUserError,
)
from app.domain.auth.entities import User, normalize_email, require_valid_password
from app.domain.auth.passwords import hash_password
from app.domain.auth.repository import AuthSessionRepository, UserRepository
from app.domain.auth.throttle import SignInThrottle


class UserService:
    """Application use cases for administrators managing users."""

    def __init__(
        self,
        users: UserRepository,
        sessions: AuthSessionRepository,
        throttle: SignInThrottle | None = None,
    ) -> None:
        self._users = users
        self._sessions = sessions
        # The running server's sign-in lock. None from the terminal (app/cli.py):
        # another process can't reach it, so a terminal reset waits out the lock.
        self._throttle = throttle

    async def list_users(self) -> list[User]:
        return await self._users.list()

    async def create_user(self, email: str, name: str, password: str, is_admin: bool) -> User:
        require_valid_password(password)
        normalized = normalize_email(email)
        if await self._users.get_by_email(normalized) is not None:
            raise EmailTakenError(f"A user with email {normalized} already exists")
        password_hash = await asyncio.to_thread(hash_password, password)
        user = User(email=normalized, name=name, password_hash=password_hash, is_admin=is_admin)
        await self._users.add(user)
        return user

    async def reset_password(self, user_id: UUID, new: str) -> None:
        require_valid_password(new)
        user = await self._require(user_id)
        user.password_hash = await asyncio.to_thread(hash_password, new)
        await self._users.update(user)
        await self._sessions.delete_for_user(user.id)
        if self._throttle is not None:
            self._throttle.clear(user.email)

    async def delete_user(self, actor: User, user_id: UUID) -> None:
        if actor.id == user_id:
            raise SelfRemovalError("You can't remove your own account")
        user = await self._require(user_id)
        await self._sessions.delete_for_user(user.id)
        await self._users.delete(user.id)

    async def _require(self, user_id: UUID) -> User:
        user = await self._users.get(user_id)
        if user is None:
            raise UnknownUserError(f"User {user_id} does not exist")
        return user
