"""The MCP tools' one way into Atlas: its own REST API, called in-process."""

from collections.abc import Mapping
from typing import Any
from urllib.parse import quote

import httpx
from fastapi import FastAPI
from mcp.server.mcpserver.exceptions import ToolError

from app.api.deps import INTERNAL_HEADER


def drop_none(**kwargs: Any) -> dict[str, Any]:
    """Query parameters without the ones the caller left out."""
    return {key: value for key, value in kwargs.items() if value is not None}


async def call_api(
    app: FastAPI,
    method: str,
    route: str,
    *,
    path: Mapping[str, str] | None = None,
    params: dict[str, Any] | None = None,
    json: dict[str, Any] | None = None,
) -> Any:
    """Call Atlas's own REST API in-process; raise the error detail on 4xx/5xx.

    `route` is the literal route template (`"/api/teams/{team_id}/metric-rules"`)
    so a static check can read which routes MCP uses; `path` fills it. Each
    value is quoted whole, so an agent-supplied id stays one path segment.
    """
    url = route.format(**{key: quote(value, safe="") for key, value in (path or {}).items()})
    # ponytail: a fresh in-process client per tool call — pool one on
    # app.state if tool latency ever matters.
    transport = httpx.ASGITransport(app=app)
    # A loopback Host: LocalOnlyMiddleware serves in-process tool calls as local.
    # The internal header stands in for a session (ADR-0028).
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://localhost",
        headers={INTERNAL_HEADER: app.state.internal_token},
    ) as client:
        response = await client.request(method, url, params=params, json=json)
    if response.status_code >= 400:
        try:
            detail = response.json().get("detail", response.text)
        except ValueError:
            detail = response.text
        # mcp 2.x masks any exception that isn't ToolError/ResourceError/MCPError
        # before it reaches the client (see mcp/server/mcpserver/tools/base.py) —
        # ToolError is what carries the REST error detail through to the model.
        raise ToolError(f"Atlas API {response.status_code}: {detail}")
    return response.json()
