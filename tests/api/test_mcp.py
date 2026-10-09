"""MCP endpoint tests.

The `client`/`test_app` fixtures don't run the app lifespan, but the MCP
session manager must be running — so these tests build their own app and
enter `session_manager.run()` explicitly. The MCP client is wired to the
app in-process via an httpx ASGITransport factory.
"""

import asyncio
import logging
from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import httpx2
import pytest
import uvicorn
from fastapi import FastAPI
from httpx import ASGITransport
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.types import TextContent
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.mcp_server import _aging_from_json
from app.api.schemas import AgingItemRead, AgingWipRead
from app.domain.metrics.aging import AgingItem, AgingWip
from app.main import _RedactSecret, create_app
from tests.api.helpers import create_team, days_ago

TOKEN = "test-token-0123456789abcdefghij"


@pytest.fixture(autouse=True)
def _drop_token_masks() -> Iterator[None]:
    """create_app() masks the token on the global uvicorn.access logger; undo it per test."""
    yield
    access = logging.getLogger("uvicorn.access")
    for mask in [f for f in access.filters if isinstance(f, _RedactSecret)]:
        access.removeFilter(mask)


@asynccontextmanager
async def running_app(
    sessionmaker: async_sessionmaker[AsyncSession],
    settings_env: Callable[..., None],
) -> AsyncIterator[FastAPI]:
    settings_env(mcp_token=TOKEN)
    app = create_app()
    app.state.sessionmaker = sessionmaker
    async with app.state.mcp.session_manager.run():
        yield app


@asynccontextmanager
async def mcp_session(app: FastAPI) -> AsyncIterator[ClientSession]:
    # mcp 2.x's streamable_http_client takes an httpx2.AsyncClient (the SDK's
    # own vendored httpx fork), not a plain httpx.AsyncClient — everything
    # else in this file still talks to the app via regular httpx.
    async with (
        httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app),
            follow_redirects=True,
        ) as http_client,
        streamable_http_client(f"http://test/mcp/{TOKEN}/", http_client=http_client) as (
            read,
            write,
        ),
        ClientSession(read, write) as session,
    ):
        await session.initialize()
        yield session


def tool_text(result: object) -> str:
    """First content block of a CallToolResult as text."""
    content = result.content[0]  # type: ignore[attr-defined]
    assert isinstance(content, TextContent)
    return content.text


def test_no_mcp_route_without_token(settings_env: Callable[..., None]) -> None:
    settings_env(mcp_token="")
    app = create_app()

    assert getattr(app.state, "mcp", None) is None
    # Route check, not a request: the SPA catch-all (if web/dist exists
    # locally) would otherwise answer and muddy a status-code assertion.
    assert not [r for r in app.routes if getattr(r, "path", "").startswith("/mcp")]


async def test_uvicorn_access_log_masks_the_token(
    sessionmaker: async_sessionmaker[AsyncSession],
    settings_env: Callable[..., None],
    caplog: pytest.LogCaptureFixture,
) -> None:
    async with running_app(sessionmaker, settings_env) as app:
        # log_config=None: keep pytest's logging (uvicorn would replace the
        # handlers); the real access logger still formats the real request.
        server = uvicorn.Server(
            uvicorn.Config(app, host="127.0.0.1", port=0, log_config=None, lifespan="off")
        )
        serving = asyncio.create_task(server.serve())
        async with asyncio.timeout(10):
            while not server.started:  # noqa: ASYNC110 — uvicorn exposes a flag, not an Event
                await asyncio.sleep(0.01)
        port = server.servers[0].sockets[0].getsockname()[1]
        try:
            with caplog.at_level(logging.INFO, logger="uvicorn.access"):
                async with httpx.AsyncClient(trust_env=False) as client:
                    await client.post(f"http://127.0.0.1:{port}/mcp/{TOKEN}/", json={})
        finally:
            server.should_exit = True
            async with asyncio.timeout(10):
                await serving

    # The mask on the global uvicorn.access logger was installed by create_app() inside
    # running_app (and is removed by the autouse _drop_token_masks fixture).
    # Only the server's access log: the client-side httpx logger echoes the URL.
    access = "\n".join(r.getMessage() for r in caplog.records if r.name == "uvicorn.access")
    assert TOKEN not in access
    assert "/mcp/***/" in access


async def test_wrong_token_is_not_served(
    sessionmaker: async_sessionmaker[AsyncSession],
    settings_env: Callable[..., None],
) -> None:
    async with running_app(sessionmaker, settings_env) as app:
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
            response = await client.post("/mcp/wrong-token/", json={})
    # 404 normally; 405 if a local web/dist build made the SPA catch-all
    # answer the path (StaticFiles rejects POST). Never 200.
    assert response.status_code in (404, 405)


async def test_list_scopes_tool(
    sessionmaker: async_sessionmaker[AsyncSession],
    settings_env: Callable[..., None],
) -> None:
    async with running_app(sessionmaker, settings_env) as app:
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
            await create_team(client)

        async with mcp_session(app) as session:
            tools = await session.list_tools()
            assert "list_scopes" in [t.name for t in tools.tools]

            result = await session.call_tool("list_scopes", {})
            assert not result.is_error
            text = tool_text(result)
            assert "Acme" in text  # organization from create_team
            assert "Platform" in text  # team from create_team
            assert "(sprint 14d)" in text  # the team's sprint_length_days rule


async def test_meeting_brief_composes_digest(
    sessionmaker: async_sessionmaker[AsyncSession],
    settings_env: Callable[..., None],
) -> None:
    async with running_app(sessionmaker, settings_env) as app:
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
            team_id = await create_team(client)

        async with mcp_session(app) as session:
            result = await session.call_tool("meeting_brief", {"team_id": team_id})
            assert not result.is_error
            text = tool_text(result)
            assert "Flow metrics" in text
            assert "Delivery health" in text
            assert "Aging WIP" in text


async def test_meeting_brief_scope_errors_surface(
    sessionmaker: async_sessionmaker[AsyncSession],
    settings_env: Callable[..., None],
) -> None:
    async with running_app(sessionmaker, settings_env) as app:  # noqa: SIM117
        # mcp_session must nest because it depends on the app from running_app.
        async with mcp_session(app) as session:
            # No scope at all -> the REST 422 detail must reach the model.
            result = await session.call_tool("meeting_brief", {})
            assert result.is_error
            assert "exactly one" in tool_text(result)

            # Unknown team -> the REST 404 detail must reach the model.
            result = await session.call_tool(
                "meeting_brief",
                {"team_id": "00000000-0000-0000-0000-000000000000"},
            )
            assert result.is_error
            assert "not found" in tool_text(result)


async def test_drilldown_tools(
    sessionmaker: async_sessionmaker[AsyncSession],
    settings_env: Callable[..., None],
) -> None:
    async with running_app(sessionmaker, settings_env) as app:
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
            team_id = await create_team(client)
            item = await client.post(
                "/api/work-items", json={"team_id": team_id, "title": "Fix login flake"}
            )
            assert item.status_code == 201

        async with mcp_session(app) as session:
            items = await session.call_tool("list_work_items", {"team_id": team_id})
            assert not items.is_error
            assert "Fix login flake" in tool_text(items)

            aging = await session.call_tool("aging_wip", {"team_id": team_id})
            assert not aging.is_error
            assert "Aging WIP" in tool_text(aging)

            fc = await session.call_tool("forecast", {"team_id": team_id})
            assert not fc.is_error
            text = tool_text(fc)
            assert "Remaining:" in text
            assert "outcomes" not in text  # the raw bucket array must never leak


async def test_run_sync_surfaces_unconfigured_connector(
    sessionmaker: async_sessionmaker[AsyncSession],
    settings_env: Callable[..., None],
) -> None:
    async with running_app(sessionmaker, settings_env) as app:
        settings_env(mcp_token=TOKEN, linear_api_key="")
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
            org = await client.post("/api/organizations", json={"name": "Acme"})
            org_id = org.json()["id"]

        async with mcp_session(app) as session:
            result = await session.call_tool("run_sync", {"organization_id": org_id})
            assert result.is_error
            # The 409-until-configured detail must reach the model verbatim.
            assert "ATLAS_LINEAR_API_KEY" in tool_text(result)


async def test_meeting_prompts(
    sessionmaker: async_sessionmaker[AsyncSession],
    settings_env: Callable[..., None],
) -> None:
    async with (
        running_app(sessionmaker, settings_env) as app,
        mcp_session(app) as session,
    ):
        prompts = await session.list_prompts()
        names = [p.name for p in prompts.prompts]
        assert {"daily_standup", "retrospective", "planning"} <= set(names)

        prompt = await session.get_prompt("daily_standup", {"team": "Platform"})
        content = prompt.messages[0].content
        assert isinstance(content, TextContent)
        assert "Platform" in content.text
        assert "meeting_brief" in content.text


async def test_retrospective_prompt_defaults_to_the_teams_sprint(
    sessionmaker: async_sessionmaker[AsyncSession],
    settings_env: Callable[..., None],
) -> None:
    async with (
        running_app(sessionmaker, settings_env) as app,
        mcp_session(app) as session,
    ):
        default = await session.get_prompt("retrospective", {"team": "Platform"})
        asked = await session.get_prompt("retrospective", {"team": "Platform", "sprint_days": "21"})

        default_text = default.messages[0].content
        asked_text = asked.messages[0].content
        assert isinstance(default_text, TextContent)
        assert isinstance(asked_text, TextContent)
        assert "last sprint" in default_text.text
        assert "sprint length" in default_text.text
        assert "window_days=the team's sprint length" in default_text.text
        assert "last 21 days" in asked_text.text
        assert "window_days=21" in asked_text.text


async def _seed_item(
    client: httpx.AsyncClient, team_id: str, title: str, *events: tuple[str, int]
) -> None:
    """A work item with (event type, days ago) events, through the REST API."""
    item = await client.post("/api/work-items", json={"team_id": team_id, "title": title})
    assert item.status_code == 201
    item_id = item.json()["id"]
    for type_, days in events:
        response = await client.post(
            "/api/events",
            json={"work_item_id": item_id, "type": type_, "occurred_at": days_ago(days)},
        )
        assert response.status_code == 201


async def test_meeting_brief_names_the_aging_history(
    sessionmaker: async_sessionmaker[AsyncSession],
    settings_env: Callable[..., None],
) -> None:
    # Review focus 5: the real tool path, not just the helpers.
    async with running_app(sessionmaker, settings_env) as app:
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
            team_id = await create_team(client)
            await _seed_item(
                client, team_id, "Shipped", ("created", 10), ("started", 6), ("completed", 2)
            )
            await _seed_item(client, team_id, "Stuck", ("created", 10), ("started", 6))

        async with mcp_session(app) as session:
            result = await session.call_tool("meeting_brief", {"team_id": team_id})
            assert not result.is_error
            text = tool_text(result)
            assert "Aging WIP (cycle-time p85 over the last 90 days = 4.0d):" in text
            (stuck,) = [line for line in text.splitlines() if line.startswith('- "Stuck"')]
            assert stuck.endswith("[over p85]")


async def test_aging_wip_tool_caps_at_fifty_without_pointing_at_itself(
    sessionmaker: async_sessionmaker[AsyncSession],
    settings_env: Callable[..., None],
) -> None:
    # Review focus 4: the full-list tool must not tell the model to call itself.
    async with running_app(sessionmaker, settings_env) as app:
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
            team_id = await create_team(client)
            for n in range(51):
                await _seed_item(client, team_id, f"Item {n}", ("created", 5), ("started", 3))

        async with mcp_session(app) as session:
            result = await session.call_tool("aging_wip", {"team_id": team_id})
            assert not result.is_error
            lines = tool_text(result).splitlines()
            assert len([line for line in lines if line.startswith("- ")]) == 50
            assert lines[-1] == "... and 1 more"


@pytest.mark.parametrize("reference", [timedelta(days=4.25), None])
def test_aging_json_rebuilds_the_domain_value(reference: timedelta | None) -> None:
    # Review focus 1-3: a non-default history and percentile, the no-reference
    # case, and the real wire format (str UUIDs/datetimes, fractional seconds).
    domain = AgingWip(
        now=datetime(2026, 10, 9, 12, tzinfo=UTC),
        cycle_time_percentile=reference,
        items=(
            AgingItem(
                work_item_id=uuid4(),
                title="Fix login\nnow",
                state="In Progress",
                age=timedelta(days=6, hours=3),
                over_percentile=reference is not None,
                assignee="Ada Lovelace",
            ),
            AgingItem(
                work_item_id=uuid4(),
                title="Docs",
                state="Review",
                age=timedelta(hours=30, seconds=0.5),
                over_percentile=False,
            ),
        ),
        percentile=70,
        history_days=30,
    )
    wire = AgingWipRead(
        now=domain.now,
        cycle_time_percentile_seconds=(
            reference.total_seconds() if reference is not None else None
        ),
        percentile=domain.percentile,
        history_days=domain.history_days,
        items=[
            AgingItemRead(
                work_item_id=item.work_item_id,
                title=item.title,
                state=item.state,
                age_seconds=item.age.total_seconds(),
                over_percentile=item.over_percentile,
                assignee=item.assignee,
            )
            for item in domain.items
        ],
    ).model_dump(mode="json")

    assert _aging_from_json(wire) == domain
