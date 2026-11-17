"""MCP configuration read tools, through a real MCP session."""

from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.codebases.entities import Codebase
from app.domain.credentials.entities import Credential, Integration
from app.domain.people.entities import Person
from app.infrastructure.repositories.codebases import SqlAlchemyCodebaseRepository
from app.infrastructure.repositories.people import SqlAlchemyPersonRepository
from tests.api.helpers import create_mcp_token, create_org_and_team, settle, store_credential
from tests.api.test_mcp import mcp_session, running_app, seed_client, tool_text


async def test_get_metric_rules_names_each_rules_source(
    file_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    # A rule change starts a history recompute: it needs the file-backed DB.
    sessionmaker = file_sessionmaker
    async with running_app(sessionmaker) as app, seed_client(app) as client:
        org_id, team_id = await create_org_and_team(client)
        await client.patch(
            f"/api/organizations/{org_id}/metric-rules", json={"aging_percentile": 90}
        )
        await client.patch(f"/api/teams/{team_id}/metric-rules", json={"forecast_history_days": 60})
        await settle(app)  # the rule change starts a history recompute
        token = await create_mcp_token(sessionmaker)
        async with mcp_session(app, token) as session:
            team = tool_text(await session.call_tool("get_metric_rules", {"team_id": team_id}))
            org = tool_text(
                await session.call_tool("get_metric_rules", {"organization_id": org_id})
            )
        await app.state.recompute_runner.close()

    assert team.startswith(f"Metric rules for team {team_id}")
    assert "- aging_percentile = 90 (workspace)" in team
    assert "- forecast_history_days = 60 (team override)" in team
    assert "- exclude_born_done = " in team
    assert "(built-in)" in team
    assert team.splitlines()[-1].startswith("History recompute: ")
    assert org.startswith(f"Metric rules for workspace {org_id}")
    assert "- aging_percentile = 90 (override)" in org
    assert "- exclude_born_done = " in org
    assert "(built-in)" in org


async def test_get_metric_rules_wants_exactly_one_scope(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    async with running_app(sessionmaker) as app:
        token = await create_mcp_token(sessionmaker)
        async with mcp_session(app, token) as session:
            both = await session.call_tool(
                "get_metric_rules", {"team_id": "a", "organization_id": "b"}
            )
            neither = await session.call_tool("get_metric_rules", {})

    for result in (both, neither):
        assert result.is_error
        assert "Provide exactly one of team_id/organization_id" in tool_text(result)


async def test_get_sync_schedule_before_any_is_saved(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    async with running_app(sessionmaker) as app, seed_client(app) as client:
        org_id, _ = await create_org_and_team(client)
        token = await create_mcp_token(sessionmaker)
        async with mcp_session(app, token) as session:
            result = await session.call_tool("get_sync_schedule", {"organization_id": org_id})

    assert tool_text(result) == "Auto sync: off."


async def test_get_sync_schedule_describes_a_saved_one(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    async with running_app(sessionmaker) as app, seed_client(app) as client:
        org_id, _ = await create_org_and_team(client)
        await client.put(
            f"/api/organizations/{org_id}/sync-schedule",
            json={
                "enabled": True,
                "days": [1, 3],
                "window_start": "08:00",
                "window_end": "18:00",
                "interval_minutes": 120,
                "timezone": "America/Sao_Paulo",
            },
        )
        token = await create_mcp_token(sessionmaker)
        async with mcp_session(app, token) as session:
            result = await session.call_tool("get_sync_schedule", {"organization_id": org_id})

    text = tool_text(result)
    assert text.startswith(
        "Auto sync: on, days Mon,Wed, 08:00\u201318:00 America/Sao_Paulo, every 120 min."
    )
    assert "Last run: never" in text


async def test_connector_status_shows_no_secret(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    await store_credential(sessionmaker, Credential(Integration.LINEAR, "lin_api_SECRET123"))
    async with running_app(sessionmaker) as app:
        token = await create_mcp_token(sessionmaker)
        async with mcp_session(app, token) as session:
            text = tool_text(await session.call_tool("connector_status", {}))

    assert "SECRET" not in text
    assert "T123" not in text
    assert "- Linear: configured" in text
    assert "- GitHub: not configured" in text
    assert "- Datadog: not configured" in text
    assert "- OpenRouter: not configured" in text


async def test_list_people_and_list_codebases_render_ids(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    async with running_app(sessionmaker) as app, seed_client(app) as client:
        org_id, _ = await create_org_and_team(client)
        person = Person(organization_id=UUID(org_id), name="Joao", display_name="João")
        codebase = Codebase(organization_id=UUID(org_id), name="atlas", external_id="r1")
        async with sessionmaker() as db:
            await SqlAlchemyPersonRepository(db).add(person)
            await SqlAlchemyCodebaseRepository(db).add(codebase)
            await db.commit()
        token = await create_mcp_token(sessionmaker)
        async with mcp_session(app, token) as session:
            people = tool_text(await session.call_tool("list_people", {"organization_id": org_id}))
            codebases = tool_text(
                await session.call_tool("list_codebases", {"organization_id": org_id})
            )
            nobody = tool_text(
                await session.call_tool("list_people", {"organization_id": str(uuid4())})
            )

    assert f"- {person.id}  João (source name: Joao)" in people
    assert (
        f'- {codebase.id}  atlas → team unmapped, prod env "production", '
        "0 PRs, 0 deployments, synced never"
    ) in codebases
    assert nobody == "No people."
