"""MCP tools that read Atlas's analytics: flow trend, bugs, forecast accuracy, one work item.

Each tool is a facade over a REST route; every scope tool takes exactly one
of team_id/project_id and leaves that validation to the REST `ScopeDep`.
"""

from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI
from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from app.api.mcp_client import call_api, drop_none
from app.domain.advisor.render import quote_title

_READ_ONLY = ToolAnnotations(read_only_hint=True)
_SECONDS_PER_DAY = 86400


def _day(iso: str) -> str:
    return iso[:10]


def _days(seconds: float | None) -> str:
    """Seconds as days with one decimal, or n/a."""
    return "n/a" if seconds is None else f"{seconds / _SECONDS_PER_DAY:.1f}d"


def _pct(rate: float | None) -> str:
    return "n/a" if rate is None else f"{rate * 100:.0f}%"


def render_flow_trend(history: dict[str, Any]) -> str:
    """A FlowHistoryRead as a header, one line per throughput bucket, and its freshness."""
    lines = [
        f"Throughput per {history['bucket_days']}-day bucket "
        f"({_day(history['window_start'])} → {_day(history['window_end'])}):"
    ]
    lines += [f"- {_day(b['start'])}: {b['completed']}" for b in history["buckets"]]
    lines.append(f"Data as of {history['data_as_of'] or 'unknown'}")
    return "\n".join(lines)


def render_bug_metrics(bugs: dict[str, Any]) -> str:
    """A BugMetricsRead as text: volumes, open bugs, then each priority."""
    per_item = "n/a" if bugs["per_item"] is None else f"{bugs['per_item']:.2f}"
    all_bugs = bugs["all_bugs"]
    lines = [
        f"Bugs created {bugs['created']}, fixed {bugs['completed']} "
        f"({_pct(bugs['share'])} of completed work; {per_item} per delivered item)",
        f"Open bugs: {all_bugs['open']}, oldest {_days(all_bugs['oldest_open_seconds'])}; "
        f"median fix {_days(all_bugs['median_seconds'])}",
    ]
    lines += [
        f"- {p['priority']}: fixed {p['fixed']}, median {_days(p['median_seconds'])}, "
        f"open {p['open']}"
        for p in bugs["priorities"]
    ]
    if bugs["created"] + bugs["completed"] < bugs["min_sample"]:
        lines.append(f"Sample below {bugs['min_sample']}: treat as indicative.")
    return "\n".join(lines)


def render_forecast_accuracy(accuracy: dict[str, Any]) -> str:
    """A ForecastAccuracyRead as one text line."""
    error = accuracy["mean_abs_error_days"]
    mean = "n/a" if error is None else f"{error:.1f}"
    return (
        f"Past forecasts evaluated: {accuracy['evaluated']} ({accuracy['pending']} pending). "
        f"p50 hit rate {_pct(accuracy['p50_hit_rate'])}, "
        f"p85 hit rate {_pct(accuracy['p85_hit_rate'])}, mean error {mean} days."
    )


def _span_seconds(start: str, end: str | None, now: datetime) -> float:
    finish = now if end is None else datetime.fromisoformat(end)
    return (finish - datetime.fromisoformat(start)).total_seconds()


def render_work_item(item: dict[str, Any], timeline: dict[str, Any]) -> str:
    """A WorkItemRead and its WorkItemTimelineRead as text."""
    now = datetime.now(UTC)
    lines = [
        f"{quote_title(item['title'])} [{item['state']}] ({item['type']}) "
        f"{item['url'] or 'no link'}",
        f"Labels: {', '.join(item['labels']) or 'none'}",
    ]
    for p in timeline["state_periods"]:
        exited = "now" if p["exited_at"] is None else _day(p["exited_at"])
        span = _days(_span_seconds(p["entered_at"], p["exited_at"], now))
        lines.append(f"- {p['state']}: {_day(p['entered_at'])} → {exited} ({span})")
    blocked = timeline["blocked_periods"]
    total = sum(_span_seconds(b["started_at"], b["ended_at"], now) for b in blocked)
    lines.append(f"Blocked: {len(blocked)} period(s), {_days(total)}")
    return "\n".join(lines)


def add_analytics_tools(mcp: MCPServer, app: FastAPI) -> None:
    @mcp.tool(annotations=_READ_ONLY)
    async def flow_trend(
        team_id: str | None = None, project_id: str | None = None, window_days: int = 90
    ) -> str:
        """Throughput over time, one count of completed items per bucket, for
        a scope. Provide exactly one of team_id/project_id. window_days is 7-365.
        """
        history = await call_api(
            app,
            "GET",
            "/api/metrics/history",
            params=drop_none(team_id=team_id, project_id=project_id, window_days=window_days),
        )
        return render_flow_trend(history)

    @mcp.tool(annotations=_READ_ONLY)
    async def bug_metrics(team_id: str) -> str:
        """A team's bug volumes, open bugs, and fix times by priority. Team only."""
        bugs = await call_api(app, "GET", "/api/metrics/bugs", params={"team_id": team_id})
        return render_bug_metrics(bugs)

    @mcp.tool(annotations=_READ_ONLY)
    async def forecast_accuracy(team_id: str | None = None, project_id: str | None = None) -> str:
        """How often past forecasts held: the share of finished work that
        landed by the p50 and p85 dates. Provide exactly one of team_id/project_id.
        """
        accuracy = await call_api(
            app,
            "GET",
            "/api/forecasts/accuracy",
            params=drop_none(team_id=team_id, project_id=project_id),
        )
        return render_forecast_accuracy(accuracy)

    @mcp.tool(annotations=_READ_ONLY)
    async def work_item(work_item_id: str) -> str:
        """One work item (id from list_work_items or aging_wip) with its state timeline
        and blocked time.
        """
        path = {"work_item_id": work_item_id}
        item = await call_api(app, "GET", "/api/work-items/{work_item_id}", path=path)
        timeline = await call_api(app, "GET", "/api/work-items/{work_item_id}/timeline", path=path)
        return render_work_item(item, timeline)
