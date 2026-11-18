from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.domain.auth.entities import AuthSession, McpToken, User


class SetupAlreadyClaimedError(Exception):
    """First-run setup was already claimed by another transaction."""


class UserRepository(Protocol):
    """Port for persisting and retrieving Users. Implemented in Infrastructure."""

    async def add(self, user: User) -> None: ...

    async def get(self, user_id: UUID) -> User | None: ...

    async def get_by_email(self, email: str) -> User | None: ...

    async def list(self) -> list[User]: ...

    async def count(self) -> int: ...

    async def update(self, user: User) -> None: ...

    async def delete(self, user_id: UUID) -> None: ...

    async def claim_setup(self, now: datetime) -> None:
        """Record that first-run setup happened; raise SetupAlreadyClaimedError if it did.

        Only one transaction can ever claim it, so two simultaneous setups
        cannot both create an admin.
        """
        ...


class AuthSessionRepository(Protocol):
    """Port for persisting sessions, keyed by token hash. Implemented in Infrastructure."""

    async def add(self, session: AuthSession) -> None: ...

    async def get(self, token_hash: str) -> AuthSession | None: ...

    async def delete(self, token_hash: str) -> None: ...

    async def delete_for_user(self, user_id: UUID, keep_token_hash: str | None = None) -> None: ...

    async def delete_expired(self, now: datetime) -> None:
        """Delete every session, of any user, whose expires_at is at or before now."""
        ...


class McpTokenRepository(Protocol):
    """Port for persisting MCP tokens, looked up by secret hash. Implemented in Infrastructure."""

    async def add(self, token: McpToken) -> None: ...

    async def get_by_hash(self, token_hash: str) -> McpToken | None: ...

    async def list_for_user(self, user_id: UUID) -> list[McpToken]:
        """The user's tokens, newest first."""
        ...

    async def delete(self, token_id: UUID, user_id: UUID) -> bool:
        """Delete the user's token; return False when that user has no such token."""
        ...

    async def touch(self, token_id: UUID, when: datetime) -> None: ...
