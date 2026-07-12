"""MCP endpoint tests.

The `client`/`test_app` fixtures don't run the app lifespan, but the MCP
session manager must be running — so these tests build their own app and
enter `session_manager.run()` explicitly. The MCP client is wired to the
app in-process via an httpx ASGITransport factory.
"""

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from httpx import ASGITransport
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from mcp.types import TextContent
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.main import create_app
from tests.api.helpers import create_team

TOKEN = "test-token-123"


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
    def factory(
        headers: dict[str, str] | None = None,
        timeout: httpx.Timeout | None = None,
        auth: httpx.Auth | None = None,
    ) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=ASGITransport(app=app),
            headers=headers,
            timeout=timeout,
            auth=auth,
            follow_redirects=True,
        )

    async with (
        streamablehttp_client(
            f"http://test/mcp/{TOKEN}/", httpx_client_factory=factory
        ) as (read, write, _),
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


async def test_wrong_token_is_not_served(
    sessionmaker: async_sessionmaker[AsyncSession],
    settings_env: Callable[..., None],
) -> None:
    async with running_app(sessionmaker, settings_env) as app:
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
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
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            await create_team(client)

        async with mcp_session(app) as session:
            tools = await session.list_tools()
            assert "list_scopes" in [t.name for t in tools.tools]

            result = await session.call_tool("list_scopes", {})
            assert not result.isError
            text = tool_text(result)
            assert "Acme" in text  # organization from create_team
            assert "Platform" in text  # team from create_team


async def test_meeting_brief_composes_digest(
    sessionmaker: async_sessionmaker[AsyncSession],
    settings_env: Callable[..., None],
) -> None:
    async with running_app(sessionmaker, settings_env) as app:
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            team_id = await create_team(client)

        async with mcp_session(app) as session:
            result = await session.call_tool("meeting_brief", {"team_id": team_id})
            assert not result.isError
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
            assert result.isError
            assert "exactly one" in tool_text(result)

            # Unknown team -> the REST 404 detail must reach the model.
            result = await session.call_tool(
                "meeting_brief",
                {"team_id": "00000000-0000-0000-0000-000000000000"},
            )
            assert result.isError
            assert "not found" in tool_text(result)


async def test_drilldown_tools(
    sessionmaker: async_sessionmaker[AsyncSession],
    settings_env: Callable[..., None],
) -> None:
    async with running_app(sessionmaker, settings_env) as app:
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            team_id = await create_team(client)
            item = await client.post(
                "/api/work-items", json={"team_id": team_id, "title": "Fix login flake"}
            )
            assert item.status_code == 201

        async with mcp_session(app) as session:
            items = await session.call_tool("list_work_items", {"team_id": team_id})
            assert not items.isError
            assert "Fix login flake" in tool_text(items)

            aging = await session.call_tool("aging_wip", {"team_id": team_id})
            assert not aging.isError
            assert "Aging WIP" in tool_text(aging)

            fc = await session.call_tool("forecast", {"team_id": team_id})
            assert not fc.isError
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
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            org = await client.post("/api/organizations", json={"name": "Acme"})
            org_id = org.json()["id"]

        async with mcp_session(app) as session:
            result = await session.call_tool("run_sync", {"organization_id": org_id})
            assert result.isError
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
