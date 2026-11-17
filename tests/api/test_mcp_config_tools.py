"""MCP configuration read tools, through a real MCP session."""

from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.auth.entities import McpAccess
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


async def test_an_agent_changes_a_team_rule_and_reads_it_back(
    file_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    sessionmaker = file_sessionmaker
    async with running_app(sessionmaker) as app, seed_client(app) as client:
        _, team_id = await create_org_and_team(client)
        token = await create_mcp_token(sessionmaker, access=McpAccess.READ_WRITE)
        async with mcp_session(app, token) as session:
            saved = tool_text(
                await session.call_tool(
                    "update_metric_rules",
                    {"team_id": team_id, "changes": {"aging_percentile": 70}},
                )
            )
            await settle(app)
            reset = tool_text(
                await session.call_tool(
                    "update_metric_rules",
                    {"team_id": team_id, "changes": {"aging_percentile": None}},
                )
            )
            await settle(app)
        await app.state.recompute_runner.close()

    assert saved.startswith("Saved.")
    assert "- aging_percentile = 70 (team override)" in saved
    assert "- aging_percentile = 70" not in reset
    assert "- aging_percentile = " in reset  # inherited again


async def test_update_metric_rules_reports_a_bad_rule_and_saves_nothing(
    file_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    sessionmaker = file_sessionmaker
    async with running_app(sessionmaker) as app, seed_client(app) as client:
        _, team_id = await create_org_and_team(client)
        token = await create_mcp_token(sessionmaker, access=McpAccess.READ_WRITE)
        async with mcp_session(app, token) as session:
            unknown = await session.call_tool(
                "update_metric_rules",
                {"team_id": team_id, "changes": {"aging_percentile": 70, "not_a_rule": 1}},
            )
            out_of_range = await session.call_tool(
                "update_metric_rules",
                {"team_id": team_id, "changes": {"aging_percentile": 500}},
            )
            current = tool_text(await session.call_tool("get_metric_rules", {"team_id": team_id}))
            neither = await session.call_tool("update_metric_rules", {"changes": {}})
        await app.state.recompute_runner.close()

    assert unknown.is_error
    assert "422" in tool_text(unknown)
    assert "not_a_rule" in tool_text(unknown)
    assert out_of_range.is_error
    assert "422" in tool_text(out_of_range)
    assert "aging_percentile" in tool_text(out_of_range)
    assert "(team override)" not in current
    assert neither.is_error
    assert "Provide exactly one of team_id/organization_id" in tool_text(neither)


async def test_a_read_token_cannot_call_write_tools(
    file_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    sessionmaker = file_sessionmaker
    async with running_app(sessionmaker) as app, seed_client(app) as client:
        _, team_id = await create_org_and_team(client)
        token = await create_mcp_token(sessionmaker, access=McpAccess.READ)
        async with mcp_session(app, token) as session:
            names = {t.name for t in (await session.list_tools()).tools}
            result = await session.call_tool(
                "update_metric_rules", {"team_id": team_id, "changes": {"aging_percentile": 70}}
            )
        rules = (await client.get(f"/api/teams/{team_id}/metric-rules")).json()

    assert "update_metric_rules" not in names
    assert "get_metric_rules" in names
    assert "run_sync" in names
    assert result.is_error
    assert "aging_percentile" not in rules["overrides"]


async def test_write_tools_carry_write_annotations(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    async with running_app(sessionmaker) as app:
        token = await create_mcp_token(sessionmaker, access=McpAccess.READ_WRITE)
        async with mcp_session(app, token) as session:
            tools = {t.name: t for t in (await session.list_tools()).tools}

    writes = {
        "update_metric_rules",
        "recompute_metric_history",
        "set_sync_schedule",
        "set_person_display_name",
        "map_codebase",
    }
    for name in writes:
        hints = tools[name].annotations
        assert hints is not None
        assert hints.read_only_hint is False
        assert hints.destructive_hint is False
        assert hints.idempotent_hint is True
    reads = tools["get_metric_rules"].annotations
    assert reads is not None
    assert reads.read_only_hint is True


async def test_set_sync_schedule_saves_and_renders(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    async with running_app(sessionmaker) as app, seed_client(app) as client:
        org_id, _ = await create_org_and_team(client)
        token = await create_mcp_token(sessionmaker, access=McpAccess.READ_WRITE)
        async with mcp_session(app, token) as session:
            text = tool_text(
                await session.call_tool(
                    "set_sync_schedule",
                    {
                        "organization_id": org_id,
                        "enabled": True,
                        "days": [1, 2, 3, 4, 5],
                        "window_start": "09:00",
                        "window_end": "18:00",
                        "interval_minutes": 60,
                        "timezone": "America/Sao_Paulo",
                    },
                )
            )

    assert text.startswith("Saved.")
    assert "Auto sync: on" in text
    assert "every 60 min" in text
    assert "Mon,Tue,Wed,Thu,Fri, 09:00\u201318:00 America/Sao_Paulo" in text


async def test_set_person_display_name_and_map_codebase(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    async with running_app(sessionmaker) as app, seed_client(app) as client:
        org_id, team_id = await create_org_and_team(client)
        person = Person(organization_id=UUID(org_id), name="Joao")
        codebase = Codebase(organization_id=UUID(org_id), name="atlas", external_id="r1")
        async with sessionmaker() as db:
            await SqlAlchemyPersonRepository(db).add(person)
            await SqlAlchemyCodebaseRepository(db).add(codebase)
            await db.commit()
        token = await create_mcp_token(sessionmaker, access=McpAccess.READ_WRITE)
        async with mcp_session(app, token) as session:
            named = tool_text(
                await session.call_tool(
                    "set_person_display_name",
                    {"person_id": str(person.id), "display_name": "João"},
                )
            )
            cleared = tool_text(
                await session.call_tool(
                    "set_person_display_name", {"person_id": str(person.id), "display_name": ""}
                )
            )
            mapped = tool_text(
                await session.call_tool(
                    "map_codebase",
                    {
                        "codebase_id": str(codebase.id),
                        "team_id": team_id,
                        "production_environment": "prod",
                    },
                )
            )
            unmapped = tool_text(
                await session.call_tool(
                    "map_codebase",
                    {
                        "codebase_id": str(codebase.id),
                        "team_id": None,
                        "production_environment": "production",
                    },
                )
            )

    assert named == "Saved: João"
    assert cleared == "Saved: Joao"
    assert f'- {codebase.id}  atlas \u2192 team {team_id}, prod env "prod"' in mapped
    assert f"- {codebase.id}  atlas \u2192 team unmapped" in unmapped


async def test_recompute_metric_history_reports_its_state(
    file_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    sessionmaker = file_sessionmaker
    async with running_app(sessionmaker) as app, seed_client(app) as client:
        org_id, _ = await create_org_and_team(client)
        token = await create_mcp_token(sessionmaker, access=McpAccess.READ_WRITE)
        async with mcp_session(app, token) as session:
            text = tool_text(
                await session.call_tool("recompute_metric_history", {"organization_id": org_id})
            )
        await settle(app)
        await app.state.recompute_runner.close()

    assert text.startswith("History recompute: ")
