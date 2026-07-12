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

    @mcp.tool()
    async def aging_wip(team_id: str | None = None, project_id: str | None = None) -> str:
        """Every in-progress item with its age, flagged when older than the
        scope's cycle-time p85 — the 'what is stuck' view for a daily
        standup. Provide exactly one of team_id/project_id.
        """
        aging = await _api(
            app,
            "GET",
            "/api/metrics/aging-wip",
            params=_params(team_id=team_id, project_id=project_id),
        )
        return _render_aging(aging, limit=50)

    @mcp.tool()
    async def list_work_items(
        team_id: str | None = None,
        project_id: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> str:
        """Page through a scope's work items (id, state, type, title).
        Use ids from here with the Atlas web UI or for follow-up questions.
        """
        page = await _api(
            app,
            "GET",
            "/api/work-items",
            params=_params(team_id=team_id, project_id=project_id, limit=limit, offset=offset),
        )
        if not page["items"]:
            return "No work items in scope."
        lines = [
            f"- {i['id']}  [{i['state']}] ({i['type']}) {i['title']}" for i in page["items"]
        ]
        lines.append(f"Showing {len(page['items'])} of {page['total']} (offset {offset}).")
        return "\n".join(lines)

    @mcp.tool()
    async def forecast(
        team_id: str | None = None,
        project_id: str | None = None,
        remaining: int | None = None,
        target_date: str | None = None,
        window_days: int = 90,
    ) -> str:
        """Monte Carlo completion forecast for a scope. Optional what-ifs:
        `remaining` overrides the open-item count (e.g. a planned sprint
        scope), `target_date` (YYYY-MM-DD) adds a hit-the-date confidence.
        Provide exactly one of team_id/project_id.
        """
        data = await _api(
            app,
            "GET",
            "/api/forecasts",
            params=_params(
                team_id=team_id,
                project_id=project_id,
                remaining=remaining,
                target_date=target_date,
                window_days=window_days,
            ),
        )
        lines = [f"Remaining: {data['remaining']} open items"]
        completion = data["completion"]
        if completion is None:
            lines.append("No completion forecast (no historical throughput in window).")
        else:
            lines.append(
                f"Completion dates ({completion['trials']} trials): "
                f"p50={completion['p50_date'][:10]}, p75={completion['p75_date'][:10]}, "
                f"p85={completion['p85_date'][:10]}, p95={completion['p95_date'][:10]}"
            )
        if data["confidence"] is not None:
            lines.append(f"Confidence of hitting target_date: {data['confidence']:.2f}")
        return "\n".join(lines)

    @mcp.tool()
    async def run_sync(organization_id: str) -> str:
        """Pull fresh data from the connected issue tracker (Linear) for an
        organization (id from list_scopes), then capture analytics
        snapshots. Run before a standup if the data may be stale. Can take
        a while on large workspaces.
        """
        summary = await _api(
            app,
            "POST",
            "/api/connectors/linear/sync",
            json={"organization_id": organization_id},
        )
        return (
            f"Sync complete: {summary['teams']} teams, {summary['projects']} projects, "
            f"{summary['work_items']} work items, {summary['events']} events, "
            f"{summary['divergences']} divergences. Snapshots captured."
        )

    def _scope_clause(team: str) -> str:
        return f" for the team named {team!r}" if team else ""

    @mcp.prompt()
    def daily_standup(team: str = "") -> str:
        """Prepare insights for today's daily standup."""
        return f"""Help me run today's daily standup{_scope_clause(team)}.

1. Call list_scopes and resolve the team (ask me if the name is ambiguous).
2. Call meeting_brief for that team, then aging_wip if the brief flags stuck items.
3. Report, in order: items over the p85 age line (by name), anything blocked,
   and how WIP compares to recent completion rate.
4. Keep it under 10 bullets, ordered by what needs a decision in the meeting.
   Flag anything the data can't answer instead of guessing."""

    @mcp.prompt()
    def retrospective(team: str = "", sprint_days: str = "14") -> str:
        """Prepare a data-grounded retrospective."""
        scope = _scope_clause(team)
        return f"""Help me prepare a retrospective{scope} covering the last {sprint_days} days.

1. Call list_scopes to resolve the team, then meeting_brief with window_days={sprint_days}.
2. Contrast this window against the trailing defaults: lead time, flow efficiency,
   blocked time, and the delivery-health components with the weakest scores.
3. Propose 2-3 discussion topics, each grounded in a number from the brief
   (quote it), phrased as an open question for the team — not a verdict.
4. Note explicitly where the window is too small to trust a trend."""

    @mcp.prompt()
    def planning(team: str = "") -> str:
        """Prepare forecast-backed input for a planning session."""
        return f"""Help me prepare for a planning session{_scope_clause(team)}.

1. Call list_scopes to resolve the team, then meeting_brief.
2. Ask me for the planned scope (item count) and/or a target date, then call
   forecast with `remaining` and/or `target_date` to test the plan.
3. Report the p50/p85/p95 completion dates and the confidence number, and say
   plainly what would have to be dropped or moved for the plan to be realistic.
4. Recommend committing at p85, not p50 — explain why in one sentence if asked."""

    return mcp
