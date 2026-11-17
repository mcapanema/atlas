"""MCP tools that read Atlas's configuration: rules, schedule, people, codebases, connectors.

Connector credentials are never read here: `connector_status` reports
configured yes/no, never a key or its hint (ADR-0032).
"""

from typing import Any

from fastapi import FastAPI
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from app.api.mcp_client import call_api, drop_none

_READ_ONLY = ToolAnnotations(read_only_hint=True)
_WEEKDAYS = {1: "Mon", 2: "Tue", 3: "Wed", 4: "Thu", 5: "Fri", 6: "Sat", 7: "Sun"}


def _rule_source(name: str, view: dict[str, Any], team: bool) -> str:
    if name in view["overrides"]:
        return "team override" if team else "override"
    if team and view["inherited"][name] != view["built_in"][name]:
        return "workspace"
    return "built-in"


def render_rules_view(view: dict[str, Any], scope_label: str, team: bool) -> str:
    """A MetricRulesViewRead as text: each effective rule with where its value comes from."""
    lines = [f"Metric rules for {scope_label}"]
    lines += [
        f"- {name} = {value} ({_rule_source(name, view, team)})"
        for name, value in sorted(view["effective"].items())
    ]
    recompute = view["recompute"]
    last = f"History recompute: {recompute['state']}"
    if recompute["state"] == "failed":
        last += f" — {recompute['error']}"
    return "\n".join([*lines, last])


def render_schedule(schedule: dict[str, Any] | None) -> str:
    """A SyncScheduleRead (or null) as one text line."""
    if schedule is None:
        return "Auto sync: off."
    days = ",".join(_WEEKDAYS[day] for day in schedule["days"])
    start, end = schedule["window_start"][:5], schedule["window_end"][:5]
    last = schedule["last_run"]
    if last is None:
        last_run = "never"
    else:
        outcome = "ok" if last["error"] is None else f"failed: {last['error']}"
        last_run = f"{last['finished_at']} ({outcome})"
    return (
        f"Auto sync: {'on' if schedule['enabled'] else 'off'}, days {days}, "
        f"{start}\u2013{end} {schedule['timezone']}, every {schedule['interval_minutes']} min. "
        f"Next run: {schedule['next_run_at'] or 'none'}. Last run: {last_run}"
    )


def render_people(people: list[dict[str, Any]]) -> str:
    if not people:
        return "No people."
    return "\n".join(
        f"- {p['id']}  {p['shown_name']}"
        + (f" (source name: {p['name']})" if p["display_name"] else "")
        for p in people
    )


def render_codebases(codebases: list[dict[str, Any]]) -> str:
    if not codebases:
        return "No codebases."
    return "\n".join(
        f"- {c['id']}  {c['name']} → team {c['team_id'] or 'unmapped'}, "
        f'prod env "{c["production_environment"]}", {c["pull_requests"]} PRs, '
        f"{c['deployments']} deployments, synced {c['last_synced_at'] or 'never'}"
        for c in codebases
    )


def render_connector_status(statuses: dict[str, dict[str, Any]]) -> str:
    """One line per connector: configured or not, what is running, never a secret."""
    detail = {"GitHub": "owner", "Datadog": "site", "OpenRouter": "model"}
    lines = []
    for name, status in statuses.items():
        line = f"- {name}: {'configured' if status['configured'] else 'not configured'}"
        if name in detail and status.get(detail[name]) and status["configured"]:
            line += f" ({detail[name]} {status[detail[name]]})"
        if status.get("running"):
            line += ", sync running"
        lines.append(line)
    return "\n".join(lines)


def add_config_read_tools(mcp: MCPServer, app: FastAPI) -> None:
    @mcp.tool(annotations=_READ_ONLY)
    async def get_metric_rules(
        team_id: str | None = None, organization_id: str | None = None
    ) -> str:
        """The metric rules in force for a team or a workspace, each with its
        source (built-in, workspace, team override). They define how every
        metric is counted. Provide exactly one of team_id/organization_id.
        """
        if team_id is not None and organization_id is None:
            view = await call_api(
                app, "GET", "/api/teams/{team_id}/metric-rules", path={"team_id": team_id}
            )
            return render_rules_view(view, f"team {team_id}", team=True)
        if organization_id is None or team_id is not None:
            raise ToolError("Provide exactly one of team_id/organization_id")
        view = await call_api(
            app,
            "GET",
            "/api/organizations/{organization_id}/metric-rules",
            path={"organization_id": organization_id},
        )
        return render_rules_view(view, f"workspace {organization_id}", team=False)

    @mcp.tool(annotations=_READ_ONLY)
    async def get_sync_schedule(organization_id: str) -> str:
        """The automatic sync schedule of an organization (id from list_scopes)."""
        schedule = await call_api(
            app,
            "GET",
            "/api/organizations/{organization_id}/sync-schedule",
            path={"organization_id": organization_id},
        )
        return render_schedule(schedule)

    @mcp.tool(annotations=_READ_ONLY)
    async def list_people(organization_id: str | None = None) -> str:
        """People work is assigned to, with ids and the name shown in Atlas."""
        people = await call_api(
            app, "GET", "/api/people", params=drop_none(organization_id=organization_id)
        )
        return render_people(people)

    @mcp.tool(annotations=_READ_ONLY)
    async def list_codebases(organization_id: str) -> str:
        """Codebases of an organization with their team mapping and production environment."""
        codebases = await call_api(
            app, "GET", "/api/codebases", params={"organization_id": organization_id}
        )
        return render_codebases(codebases)

    @mcp.tool(annotations=_READ_ONLY)
    async def connector_status() -> str:
        """Which connectors (Linear, GitHub, Datadog, OpenRouter) are configured.
        Never shows a key.
        """
        statuses = {
            "Linear": await call_api(app, "GET", "/api/connectors/linear"),
            "GitHub": await call_api(app, "GET", "/api/connectors/github"),
            "Datadog": await call_api(app, "GET", "/api/connectors/datadog"),
            "OpenRouter": await call_api(app, "GET", "/api/connectors/openrouter"),
        }
        return render_connector_status(statuses)
