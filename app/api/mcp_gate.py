"""The MCP endpoint's door: a user's token in the path picks the server (ADR-0032)."""

from collections.abc import Mapping

from fastapi import FastAPI
from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.api.deps import mcp_token_service_for
from app.domain.auth.entities import McpAccess


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
            access = await mcp_token_service_for(session).authenticate(
                scope["path_params"]["token"]
            )
            await session.commit()  # last_used_at
        if access is None:
            # The same answer as any unknown path: a wrong token reveals nothing.
            await PlainTextResponse("Not Found", status_code=404)(scope, receive, send)
            return
        await self._apps[access](scope, receive, send)
