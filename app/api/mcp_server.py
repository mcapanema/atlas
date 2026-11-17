"""MCP server: chat access to Atlas for Claude / ChatGPT connectors.

Every tool is a thin facade over Atlas's own REST API, called in-process
through an ASGI transport — scope validation (exactly-one-of
team_id/project_id, 404 on unknown ids), DTO serialization, and error
semantics (409-until-configured, 502 upstream) are reused, never
re-implemented. Tools return compact text, not raw JSON: chat-client
context windows are the scarce resource this module is designed around.

Served at /mcp/<token>/ by create_app(), one server per access level;
`McpGate` (mcp_gate.py) checks the user's token and picks the server
(ADR-0032). The token rides in the URL because claude.ai and ChatGPT
connector UIs cannot send custom headers.
"""

import asyncio
from datetime import timedelta
from typing import Any

from fastapi import FastAPI
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from app.api.mcp_analytics_tools import add_analytics_tools
from app.api.mcp_client import call_api, drop_none
from app.api.mcp_config_tools import add_config_read_tools, add_config_write_tools
from app.api.schemas import AgingWipRead, DoraMetricsRead
from app.domain.advisor.render import quote_title, render_aging, render_dora
from app.domain.auth.entities import McpAccess
from app.domain.metrics.aging import AgingItem, AgingWip
from app.domain.metrics.dora import DoraMetrics
from app.domain.metrics.windows import STATS_WINDOW_DAYS

_READ_ONLY = ToolAnnotations(read_only_hint=True)
# run_sync writes synced data, not settings: it is on both servers (ADR-0032).
_SYNC = ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=True)

_INSTRUCTIONS = (
    "Atlas is a delivery-intelligence platform for Engineering Managers: "
    "flow metrics, delivery health, aging WIP, and Monte Carlo forecasts "
    "computed from synced issue-tracker data. Typical flow: call list_scopes "
    "to resolve a team or project by name, then meeting_brief for the "
    "one-call digest; drill down with the other tools only when asked. "
    "Call get_metric_rules before explaining a metric — the rules define how it is counted."
)

_WRITE_INSTRUCTIONS = (
    " Before a write, show the user the current value and the change, "
    "and wait for their confirmation."
)

# run_sync's wait for the background sync job: long enough for a typical
# sync, short of a chat client's tool-call timeout.
RUN_SYNC_WAIT_SECONDS = 45.0
RUN_SYNC_POLL_SECONDS = 1.0


def _render_health(health: dict[str, Any]) -> str:
    if health["score"] is None:
        return "Delivery health: not enough data to score."
    lines = [f"Delivery health: {health['score']}/100 ({health['band']})"]
    lines += [f"- {c['name']} {c['score']}: {c['reason']}" for c in health["components"]]
    return "\n".join(lines)


def _dora_from_json(data: dict[str, Any]) -> DoraMetrics:
    """GET /api/metrics/dora's JSON back as the domain value, for render_dora."""
    dto = DoraMetricsRead.model_validate(data)
    lead, restore = dto.lead_time_median_seconds, dto.restore_median_seconds
    return DoraMetrics(
        **dto.model_dump(exclude={"lead_time_median_seconds", "restore_median_seconds"}),
        lead_time_median=timedelta(seconds=lead) if lead is not None else None,
        restore_median=timedelta(seconds=restore) if restore is not None else None,
    )


def _aging_from_json(data: dict[str, Any]) -> AgingWip:
    """GET /api/metrics/aging-wip's JSON back as the domain value, for render_aging."""
    dto = AgingWipRead.model_validate(data)
    seconds = dto.cycle_time_percentile_seconds
    median = dto.cycle_time_median_seconds
    return AgingWip(
        now=dto.now,
        cycle_time_percentile=timedelta(seconds=seconds) if seconds is not None else None,
        items=tuple(
            AgingItem(
                work_item_id=item.work_item_id,
                title=item.title,
                state=item.state,
                age=timedelta(seconds=item.age_seconds),
                over_percentile=item.over_percentile,
                assignee=item.assignee,
                blocked=item.blocked,
                over_median=item.over_median,
                type=item.type,
            )
            for item in dto.items
        ),
        percentile=dto.percentile,
        history_days=dto.history_days,
        cycle_time_median=timedelta(seconds=median) if median is not None else None,
    )


async def _wait_for_job(app: FastAPI, job: dict[str, Any]) -> dict[str, Any]:
    """Poll a sync job until it finishes or RUN_SYNC_WAIT_SECONDS pass; its last read."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + RUN_SYNC_WAIT_SECONDS
    while job["state"] == "running" and loop.time() < deadline:
        await asyncio.sleep(RUN_SYNC_POLL_SECONDS)
        job = await call_api(
            app, "GET", "/api/connectors/linear/jobs/{job_id}", path={"job_id": job["id"]}
        )
    return job


def _render_sync_job(job: dict[str, Any]) -> str:
    if job["state"] == "running":
        # Phase is unset only before the job's first step.
        phase = job["phase"] or "starting"
        return (
            f"Sync still running (phase: {phase}). Call run_sync again in a minute for its outcome."
        )
    if job["state"] == "failed":
        raise ToolError(f"Sync failed: {job['error']}")
    summary = job["summary"]
    return (
        f"Sync complete: {summary['teams']} teams, {summary['projects']} projects, "
        f"{summary['work_items']} work items, {summary['events']} events, "
        f"{summary['divergences']} divergences, {summary['deleted']} deleted. "
        "Snapshots captured."
    )


def _register_prompts(mcp: MCPServer) -> None:
    """Register meeting prompts with the MCP server."""

    def _scope_clause(team: str) -> str:
        return f" for the team named {team!r}" if team else ""

    @mcp.prompt()
    def daily_standup(team: str = "") -> str:
        """Prepare insights for today's daily standup."""
        return f"""Help me run today's daily standup{_scope_clause(team)}.

1. Call list_scopes and resolve the team (ask me if the name is ambiguous).
2. Call meeting_brief for that team, then aging_wip if the brief flags stuck items.
3. Report, in order: items over the aging percentile line (by name), anything blocked,
   and how WIP compares to recent completion rate.
4. Keep it under 10 bullets, ordered by what needs a decision in the meeting.
   Flag anything the data can't answer instead of guessing."""

    @mcp.prompt()
    def retrospective(team: str = "", sprint_days: str = "") -> str:
        """Prepare a data-grounded retrospective over the team's last sprint."""
        scope = _scope_clause(team)
        span = f"last {sprint_days} days" if sprint_days else "last sprint"
        window = sprint_days or "the team's sprint length (list_scopes shows it)"
        return f"""Help me prepare a retrospective{scope} covering the {span}.

1. Call list_scopes to resolve the team, then meeting_brief with window_days={window}.
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


def _add_dora_tool(mcp: MCPServer, app: FastAPI) -> None:
    @mcp.tool(annotations=_READ_ONLY)
    async def dora(team_id: str) -> str:
        """The team's DORA metrics — deploy frequency, change lead time, change
        failure rate and time to restore — with their DORA bands. Team only.
        """
        data = await call_api(app, "GET", "/api/metrics/dora", params={"team_id": team_id})
        return render_dora(_dora_from_json(data))


def _instructions(access: McpAccess) -> str:
    return _INSTRUCTIONS + (_WRITE_INSTRUCTIONS if access is McpAccess.READ_WRITE else "")


def _add_config_tools(mcp: MCPServer, app: FastAPI, access: McpAccess) -> None:
    add_config_read_tools(mcp, app)
    if access is McpAccess.READ_WRITE:
        add_config_write_tools(mcp, app)


def build_mcp_server(app: FastAPI, access: McpAccess) -> MCPServer:
    """The MCP server for one access level, its tools closing over the FastAPI app they front."""
    # mcp 2.x: FastMCP was renamed to MCPServer, and the transport-mode
    # kwargs (stateless_http, json_response, streamable_http_path,
    # transport_security) moved off the constructor onto
    # streamable_http_app() — see app/main.py's mount call for where those
    # now live. stateless + json_response: every request self-contained,
    # plain JSON replies — the simplest mode for connector clients and
    # tests alike. streamable_http_path="/" so the endpoint is exactly the
    # mount path. transport_security: MCPServer auto-enables Host/Origin
    # allowlisting (DNS-rebinding protection) whenever host="127.0.0.1"
    # (the default), rejecting any Host header outside
    # 127.0.0.1/localhost/::1 — but this server is mounted inside Atlas's
    # own app under whatever hostname Atlas is deployed at, never bound to
    # its own localhost socket. The per-user path token is the actual auth
    # boundary (see module docstring), so the allowlist has no
    # deployment-specific value here.
    mcp = MCPServer(
        name="Atlas",
        instructions=_instructions(access),
    )
    _add_dora_tool(mcp, app)
    _add_config_tools(mcp, app, access)
    add_analytics_tools(mcp, app)

    @mcp.tool(annotations=_READ_ONLY)
    async def list_scopes() -> str:
        """List all organizations, teams, and projects with their ids.

        Call this first to resolve a team or project name into the id the
        other tools require.
        """
        orgs = await call_api(app, "GET", "/api/organizations")
        teams = await call_api(app, "GET", "/api/teams")
        projects = await call_api(app, "GET", "/api/projects")
        lines = ["Organizations:"]
        lines += [f"- {o['id']}  {o['name']}" for o in orgs] or ["- (none)"]
        lines.append("Teams:")
        lines += [
            f"- {t['id']}  {t['name']} (sprint {t['sprint_length_days']}d)" for t in teams
        ] or ["- (none)"]
        lines.append("Projects:")
        lines += [
            f"- {p['id']}  {p['name']} (teams {', '.join(p['team_ids'])})" for p in projects
        ] or ["- (none)"]
        return "\n".join(lines)

    @mcp.tool(annotations=_READ_ONLY)
    async def meeting_brief(
        team_id: str | None = None,
        project_id: str | None = None,
        window_days: int = STATS_WINDOW_DAYS,
    ) -> str:
        """One-call delivery brief for a team or project — flow metrics,
        lead-time distribution, Monte Carlo forecast, DORA metrics (team only),
        delivery health, and aging WIP. Provide exactly one of team_id/project_id (from
        list_scopes). Use this for daily standups, retros, reviews, and
        planning before reaching for any drill-down tool. For a retrospective,
        pass the team's sprint length (shown by list_scopes) as window_days.
        """
        scope = drop_none(team_id=team_id, project_id=project_id)
        context = await call_api(
            app,
            "GET",
            "/api/recommendations/context",
            params={**scope, "window_days": window_days},
        )
        health = await call_api(
            app, "GET", "/api/metrics/health", params={**scope, "window_days": window_days}
        )
        aging = await call_api(app, "GET", "/api/metrics/aging-wip", params=scope)
        return "\n\n".join(
            [
                context["context"],
                _render_health(health),
                render_aging(
                    _aging_from_json(aging),
                    more_hint=" (use aging_wip for the full list)",
                    show_ids=True,
                ),
            ]
        )

    @mcp.tool(annotations=_READ_ONLY)
    async def aging_wip(team_id: str | None = None, project_id: str | None = None) -> str:
        """Every in-progress item with its age, flagged when older than the
        scope's configured aging percentile of cycle time or blocked right now — the 'what is
        stuck' view for a daily standup. Each line starts with the work item id (open it
        with work_item) and names the assignee. Provide exactly one of team_id/project_id.
        """
        aging = await call_api(
            app,
            "GET",
            "/api/metrics/aging-wip",
            params=drop_none(team_id=team_id, project_id=project_id),
        )
        return render_aging(_aging_from_json(aging), limit=50, show_ids=True)

    @mcp.tool(annotations=_READ_ONLY)
    async def list_work_items(
        team_id: str | None = None,
        project_id: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> str:
        """Page through a scope's work items (id, state, type, title).
        Use ids from here with the Atlas web UI or for follow-up questions.
        """
        page = await call_api(
            app,
            "GET",
            "/api/work-items",
            params=drop_none(team_id=team_id, project_id=project_id, limit=limit, offset=offset),
        )
        if not page["items"]:
            return "No work items in scope."
        lines = [
            f"- {i['id']}  [{i['state']}] ({i['type']}) {quote_title(i['title'])}"
            for i in page["items"]
        ]
        lines.append(f"Showing {len(page['items'])} of {page['total']} (offset {offset}).")
        return "\n".join(lines)

    @mcp.tool(annotations=_READ_ONLY)
    async def forecast(
        team_id: str | None = None,
        project_id: str | None = None,
        remaining: int | None = None,
        target_date: str | None = None,
        window_days: int | None = None,
    ) -> str:
        """Monte Carlo completion forecast for a scope. Optional what-ifs:
        `remaining` overrides the open-item count (e.g. a planned sprint
        scope), `target_date` (YYYY-MM-DD) adds a hit-the-date confidence.
        `window_days` defaults to the team's forecast history rule.
        Provide exactly one of team_id/project_id.
        """
        data = await call_api(
            app,
            "GET",
            "/api/forecasts",
            params=drop_none(
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

    @mcp.tool(annotations=_SYNC)
    async def run_sync(organization_id: str) -> str:
        """Pull fresh data from the connected issue tracker (Linear) for an
        organization (id from list_scopes), then capture analytics
        snapshots. Run before a standup if the data may be stale. The sync
        runs in the background; this waits up to 45 s for its outcome. If
        it is still running then, call run_sync again later: the second
        call attaches to the running sync instead of starting another.
        """
        job = await call_api(
            app,
            "POST",
            "/api/connectors/linear/sync",
            json={"organization_id": organization_id},
        )
        return _render_sync_job(await _wait_for_job(app, job))

    _register_prompts(mcp)
    return mcp
