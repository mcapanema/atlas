"""The MCP endpoint's door: a user's token in the path picks the server (ADR-0032)."""

import logging
from collections.abc import Mapping

from fastapi import FastAPI
from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.api.deps import mcp_token_service_for
from app.domain.auth.entities import McpAccess

logger = logging.getLogger(__name__)


class McpGate:
    """Mounted at `/mcp/{token}`: forward to the MCP app for the token's access level.

    One MCP app per level, not one app told the level per request: in
    stateless mode the SDK runs tools in its session manager's own task
    group, so a contextvar set here would not reach them.
    """

    def __init__(self, app: FastAPI, apps: Mapping[McpAccess, ASGIApp]) -> None:
        self._app = app
        self._apps = apps

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        # Read at request time: tests swap the sessionmaker after create_app().
        async with self._app.state.sessionmaker() as session:
            # A failed lookup raises: the gate fails closed.
            access = await mcp_token_service_for(session).authenticate(
                scope["path_params"]["token"]
            )
            try:
                await session.commit()  # last_used_at, best effort
            except Exception:  # noqa: BLE001 — a lost last_used_at must not deny a valid token
                await session.rollback()
                logger.warning("Could not record when an MCP token was last used")
        if access is None:
            # The same answer as any unknown path: a wrong token reveals nothing.
            await PlainTextResponse("Not Found", status_code=404)(scope, receive, send)
            return
        await self._apps[access](scope, receive, send)
