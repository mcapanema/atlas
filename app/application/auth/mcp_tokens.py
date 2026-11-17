from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.domain._time import utcnow
from app.domain.auth.entities import McpAccess, McpToken, User
from app.domain.auth.repository import McpTokenRepository
from app.domain.auth.tokens import hash_token, new_mcp_token

_HINT_LENGTH = 4


class UnknownMcpTokenError(Exception):
    """The user has no MCP token with this id."""


@dataclass(frozen=True)
class IssuedMcpToken:
    token: McpToken
    secret: str


class McpTokenService:
    """Application use cases for a user's MCP tokens (ADR-0028)."""

    def __init__(self, tokens: McpTokenRepository, now: Callable[[], datetime] = utcnow) -> None:
        self._tokens = tokens
        self._now = now

    async def issue(self, user: User, name: str, access: McpAccess) -> IssuedMcpToken:
        secret, token_hash = new_mcp_token()
        token = McpToken(
            user_id=user.id,
            name=name,
            access=access,
            token_hash=token_hash,
            hint=secret[-_HINT_LENGTH:],
            created_at=self._now(),
        )
        await self._tokens.add(token)
        return IssuedMcpToken(token, secret)

    async def list(self, user: User) -> list[McpToken]:
        return await self._tokens.list_for_user(user.id)

    async def revoke(self, user: User, token_id: UUID) -> None:
        if not await self._tokens.delete(token_id, user.id):
            raise UnknownMcpTokenError(f"MCP token {token_id} not found")

    async def authenticate(self, secret: str) -> McpAccess | None:
        token = await self._tokens.get_by_hash(hash_token(secret))
        if token is None:
            return None
        now = self._now()
        if token.needs_touch(now):
            await self._tokens.touch(token.id, now)
        return token.access
