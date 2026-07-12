"""MCP server: chat access to Atlas for Claude / ChatGPT connectors.

Every tool is a thin facade over Atlas's own REST API, called in-process
through an ASGI transport — scope validation (exactly-one-of
team_id/project_id, 404 on unknown ids), DTO serialization, and error
semantics (409-until-configured, 502 upstream) are reused, never
re-implemented. Tools return compact text, not raw JSON: chat-client
context windows are the scarce resource this module is designed around.

Mounted at /mcp/<ATLAS_MCP_TOKEN> by create_app(); the token is the only
authentication (claude.ai and ChatGPT connector UIs cannot send custom
headers — the secret has to live in the URL).
"""

from typing import Any

import httpx
from fastapi import FastAPI
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

_INSTRUCTIONS = (
    "Atlas is a delivery-intelligence platform for Engineering Managers: "
    "flow metrics, delivery health, aging WIP, and Monte Carlo forecasts "
    "computed from synced issue-tracker data. Typical flow: call list_scopes "
    "to resolve a team or project by name, then meeting_brief for the "
    "one-call digest; drill down with the other tools only when asked."
)


def _params(**kwargs: Any) -> dict[str, Any]:
    return {key: value for key, value in kwargs.items() if value is not None}


_DAY_SECONDS = 86400


def _render_health(health: dict[str, Any]) -> str:
    if health["score"] is None:
        return "Delivery health: not enough data to score."
    lines = [f"Delivery health: {health['score']}/100 ({health['band']})"]
    lines += [f"- {c['name']} {c['score']}: {c['reason']}" for c in health["components"]]
    return "\n".join(lines)


def _render_aging(aging: dict[str, Any], limit: int = 10) -> str:
    items = aging["items"]
    if not items:
        return "Aging WIP: nothing in progress."
    p85 = aging["cycle_time_p85_seconds"]
    header = "Aging WIP"
    if p85 is not None:
        header += f" (cycle-time p85 = {p85 / _DAY_SECONDS:.1f}d)"
    lines = [header + ":"]
    for item in items[:limit]:
        age = item["age_seconds"] / _DAY_SECONDS
        flag = " [over p85]" if item["over_p85"] else ""
        lines.append(f"- {item['title']} — {item['state']}, {age:.1f}d{flag}")
    if len(items) > limit:
        lines.append(f"... and {len(items) - limit} more (use aging_wip for the full list)")
    return "\n".join(lines)


async def _api(
    app: FastAPI,
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    json: dict[str, Any] | None = None,
) -> Any:
    """Call Atlas's own REST API in-process; raise the error detail on 4xx/5xx."""
    # ponytail: a fresh in-process client per tool call — pool one on
    # app.state if tool latency ever matters.
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://atlas") as client:
        response = await client.request(method, path, params=params, json=json)
    if response.status_code >= 400:
        try:
            detail = response.json().get("detail", response.text)
        except ValueError:
            detail = response.text
        raise RuntimeError(f"Atlas API {response.status_code}: {detail}")
    return response.json()


def build_mcp_server(app: FastAPI) -> FastMCP:
    """The MCP server, its tools closing over the FastAPI app they front."""
    # stateless + json_response: every request self-contained, plain JSON
    # replies — the simplest mode for connector clients and tests alike.
    # streamable_http_path="/" so the endpoint is exactly the mount path.
    # transport_security: FastMCP auto-enables Host/Origin allowlisting
    # (DNS-rebinding protection) whenever host="127.0.0.1" (the default),
    # rejecting any Host header outside 127.0.0.1/localhost/::1 — but this
    # server is mounted inside Atlas's own app under whatever hostname
    # Atlas is deployed at, never bound to its own localhost socket. The
    # secret path token is the actual auth boundary (see module docstring),
    # so the allowlist has no deployment-specific value here.
    mcp = FastMCP(
        name="Atlas",
        instructions=_INSTRUCTIONS,
        stateless_http=True,
        json_response=True,
        streamable_http_path="/",
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )

    @mcp.tool()
    async def list_scopes() -> str:
        """List all organizations, teams, and projects with their ids.

        Call this first to resolve a team or project name into the id the
        other tools require.
        """
        orgs = await _api(app, "GET", "/api/organizations")
        teams = await _api(app, "GET", "/api/teams")
        projects = await _api(app, "GET", "/api/projects")
        lines = ["Organizations:"]
        lines += [f"- {o['id']}  {o['name']}" for o in orgs] or ["- (none)"]
        lines.append("Teams:")
        lines += [f"- {t['id']}  {t['name']}" for t in teams] or ["- (none)"]
        lines.append("Projects:")
        lines += [
            f"- {p['id']}  {p['name']} (team {p['team_id']})" for p in projects
        ] or ["- (none)"]
        return "\n".join(lines)

    @mcp.tool()
    async def meeting_brief(
        team_id: str | None = None,
        project_id: str | None = None,
        window_days: int = 30,
    ) -> str:
        """One-call delivery brief for a team or project — flow metrics,
        lead-time distribution, Monte Carlo forecast, delivery health, and
        aging WIP. Provide exactly one of team_id/project_id (from
        list_scopes). Use this for daily standups, retros, reviews, and
        planning before reaching for any drill-down tool.
        """
        scope = _params(team_id=team_id, project_id=project_id)
        context = await _api(
            app,
            "GET",
            "/api/recommendations/context",
            params={**scope, "window_days": window_days},
        )
        health = await _api(
            app, "GET", "/api/metrics/health", params={**scope, "window_days": window_days}
        )
        aging = await _api(app, "GET", "/api/metrics/aging-wip", params=scope)
        return "\n\n".join(
            [context["context"], _render_health(health), _render_aging(aging)]
        )

    return mcp
