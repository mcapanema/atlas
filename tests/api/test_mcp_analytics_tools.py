"""MCP analytics read tools, through a real MCP session."""

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.api.helpers import create_mcp_token, create_org_and_team, days_ago
from tests.api.test_mcp import mcp_session, running_app, seed_client, tool_text


async def _seed_item(
    client: httpx.AsyncClient, team_id: str, title: str, *events: tuple[str, int]
) -> str:
    item = await client.post("/api/work-items", json={"team_id": team_id, "title": title})
    assert item.status_code == 201
    item_id: str = item.json()["id"]
    for type_, days in events:
        response = await client.post(
            "/api/events",
            json={"work_item_id": item_id, "type": type_, "occurred_at": days_ago(days)},
        )
        assert response.status_code == 201
    return item_id


async def test_flow_trend_lists_each_bucket(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    async with running_app(sessionmaker) as app, seed_client(app) as client:
        _, team_id = await create_org_and_team(client)
        await _seed_item(client, team_id, "Shipped", ("created", 10), ("completed", 2))
        token = await create_mcp_token(sessionmaker)
        async with mcp_session(app, token) as session:
            text = tool_text(await session.call_tool("flow_trend", {"team_id": team_id}))

    lines = text.splitlines()
    assert lines[0].startswith("Throughput per ")
    assert "-day bucket (" in lines[0]
    assert " → " in lines[0]
    buckets = [line for line in lines if line.startswith("- ")]
    assert buckets
    assert sum(int(line.rsplit(": ", 1)[1]) for line in buckets) == 1
    assert lines[-1].startswith("Data as of ")


async def test_bug_metrics_marks_a_small_sample(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    async with running_app(sessionmaker) as app, seed_client(app) as client:
        _, team_id = await create_org_and_team(client)
        token = await create_mcp_token(sessionmaker)
        async with mcp_session(app, token) as session:
            text = tool_text(await session.call_tool("bug_metrics", {"team_id": team_id}))

    assert text.startswith("Bugs created 0, fixed 0 (")
    assert "Open bugs: 0, oldest n/a; median fix n/a" in text
    assert "Sample below " in text
    assert "treat as indicative." in text


async def test_forecast_accuracy_with_no_history_says_na(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    async with running_app(sessionmaker) as app, seed_client(app) as client:
        _, team_id = await create_org_and_team(client)
        token = await create_mcp_token(sessionmaker)
        async with mcp_session(app, token) as session:
            text = tool_text(await session.call_tool("forecast_accuracy", {"team_id": team_id}))

    assert text.startswith("Past forecasts evaluated: 0 (0 pending).")
    assert "p50 hit rate n/a" in text
    assert "p85 hit rate n/a" in text


async def test_work_item_shows_its_state_timeline(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    async with running_app(sessionmaker) as app, seed_client(app) as client:
        _, team_id = await create_org_and_team(client)
        item_id = await _seed_item(client, team_id, "Fix the thing", ("created", 10))
        for payload in [
            {
                "type": "started",
                "occurred_at": days_ago(6),
                "from_state": "Backlog",
                "to_state": "In Progress",
            },
            {"type": "blocked", "occurred_at": days_ago(4)},
            {"type": "unblocked", "occurred_at": days_ago(3)},
        ]:
            response = await client.post("/api/events", json={"work_item_id": item_id, **payload})
            assert response.status_code == 201
        token = await create_mcp_token(sessionmaker)
        async with mcp_session(app, token) as session:
            text = tool_text(await session.call_tool("work_item", {"work_item_id": item_id}))

    lines = text.splitlines()
    assert lines[0].endswith("no link")
    assert "Fix the thing" in lines[0]
    assert lines[1].startswith("Labels: ")
    periods = [line for line in lines if line.startswith("- ")]
    assert len(periods) >= 2
    assert all(" → " in line and line.endswith("d)") for line in periods)
    assert lines[-1] == "Blocked: 1 period(s), 1.0d"
    assert periods[-1].startswith("- In Progress: ")
    assert " → now (" in periods[-1]


async def test_an_unknown_work_item_is_a_tool_error(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    async with running_app(sessionmaker) as app:
        token = await create_mcp_token(sessionmaker)
        async with mcp_session(app, token) as session:
            result = await session.call_tool(
                "work_item", {"work_item_id": "00000000-0000-0000-0000-000000000000"}
            )

    assert result.is_error
    assert "404" in tool_text(result)
