"""MCP tools that read Atlas's configuration: rules, schedule, people, codebases, connectors.

Connector credentials are never read or written here: `connector_status` reports
configured yes/no, never a key or its hint (ADR-0032).
"""

from typing import Any

from fastapi import FastAPI
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from app.api.mcp_client import call_api, drop_none

_READ_ONLY = ToolAnnotations(read_only_hint=True)
_WRITE = ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=True)
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


def add_config_write_tools(mcp: MCPServer, app: FastAPI) -> None:
    """Registered only on the read-write server (ADR-0032)."""

    @mcp.tool(annotations=_WRITE)
    async def update_metric_rules(
        changes: dict[str, Any],
        team_id: str | None = None,
        organization_id: str | None = None,
    ) -> str:
        """Change metric rules of a team or a workspace. `changes` maps rule
        names to values; null makes a rule inherit again. Provide exactly one of
        team_id/organization_id. Call get_metric_rules first for the rule names
        and current values. Changing a rule rewrites the scope's metric history
        in the background.
        """
        if team_id is not None and organization_id is None:
            view = await call_api(
                app,
                "PATCH",
                "/api/teams/{team_id}/metric-rules",
                path={"team_id": team_id},
                json=changes,
            )
            return "Saved.\n" + render_rules_view(view, f"team {team_id}", team=True)
        if organization_id is None or team_id is not None:
            raise ToolError("Provide exactly one of team_id/organization_id")
        view = await call_api(
            app,
            "PATCH",
            "/api/organizations/{organization_id}/metric-rules",
            path={"organization_id": organization_id},
            json=changes,
        )
        return "Saved.\n" + render_rules_view(view, f"workspace {organization_id}", team=False)

    @mcp.tool(annotations=_WRITE)
    async def recompute_metric_history(organization_id: str) -> str:
        """Rebuild the metric history of every scope of an organization in the
        background, with the rules now in force.
        """
        view = await call_api(
            app,
            "POST",
            "/api/organizations/{organization_id}/metric-rules/recompute",
            path={"organization_id": organization_id},
        )
        return f"History recompute: {view['recompute']['state']}"

    @mcp.tool(annotations=_WRITE)
    async def set_sync_schedule(
        organization_id: str,
        enabled: bool,
        days: list[int],
        window_start: str,
        window_end: str,
        interval_minutes: int,
        timezone: str,
    ) -> str:
        """Set the automatic sync schedule of an organization. This replaces
        the whole schedule, so call get_sync_schedule first. `days` are ISO
        weekdays (1 = Monday ... 7 = Sunday); times are HH:MM in `timezone`
        (an IANA name such as America/Sao_Paulo).
        """
        schedule = await call_api(
            app,
            "PUT",
            "/api/organizations/{organization_id}/sync-schedule",
            path={"organization_id": organization_id},
            json={
                "enabled": enabled,
                "days": days,
                "window_start": window_start,
                "window_end": window_end,
                "interval_minutes": interval_minutes,
                "timezone": timezone,
            },
        )
        return "Saved.\n" + render_schedule(schedule)

    @mcp.tool(annotations=_WRITE)
    async def set_person_display_name(person_id: str, display_name: str) -> str:
        """Set the name Atlas shows for a person (id from list_people). A blank
        name clears it, and Atlas shows the source name again.
        """
        person = await call_api(
            app,
            "PATCH",
            "/api/people/{person_id}",
            path={"person_id": person_id},
            json={"display_name": display_name},
        )
        return f"Saved: {person['shown_name']}"

    @mcp.tool(annotations=_WRITE)
    async def map_codebase(
        codebase_id: str, team_id: str | None, production_environment: str
    ) -> str:
        """Map a codebase (id from list_codebases) to a team, and name the
        deployment environment that counts as production. A null team_id
        unmaps the codebase.
        """
        codebase = await call_api(
            app,
            "PUT",
            "/api/codebases/{codebase_id}",
            path={"codebase_id": codebase_id},
            json={"team_id": team_id, "production_environment": production_environment},
        )
        return render_codebases([codebase])
