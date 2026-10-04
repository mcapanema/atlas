from datetime import UTC, datetime, timedelta

from fastapi import FastAPI
from httpx import AsyncClient

from tests.api.helpers import create_team, settle


async def _set(app: FastAPI, client: AsyncClient, team: str, **rules: object) -> None:
    response = await client.patch(f"/api/teams/{team}/metric-rules", json=rules)
    assert response.status_code == 200
    await settle(app)


async def test_dates_resolve_in_the_teams_timezone(
    rules_app: FastAPI, rules_client: AsyncClient
) -> None:
    team = await create_team(rules_client)
    await _set(rules_app, rules_client, team, timezone="America/Sao_Paulo")

    body = (
        await rules_client.get(
            "/api/metrics", params={"team_id": team, "start": "2026-07-01", "end": "2026-07-01"}
        )
    ).json()

    assert datetime.fromisoformat(body["window_end"]) == datetime(2026, 7, 2, 3, tzinfo=UTC)


async def test_forecast_history_defaults_to_the_teams_rule(
    rules_app: FastAPI, rules_client: AsyncClient
) -> None:
    team = await create_team(rules_client)
    await _set(rules_app, rules_client, team, forecast_history_days=30)

    body = (await rules_client.get("/api/forecasts", params={"team_id": team})).json()

    span = datetime.fromisoformat(body["window_end"]) - datetime.fromisoformat(body["window_start"])
    assert span == timedelta(days=30)


async def test_teams_list_flags_custom_rules(rules_app: FastAPI, rules_client: AsyncClient) -> None:
    team = await create_team(rules_client)
    before = (await rules_client.get("/api/teams")).json()

    await _set(rules_app, rules_client, team, aging_percentile=70)
    after = (await rules_client.get("/api/teams")).json()

    assert [t["has_custom_rules"] for t in before] == [False]
    assert [t["has_custom_rules"] for t in after] == [True]


async def test_aging_wip_reports_its_percentile(
    rules_app: FastAPI, rules_client: AsyncClient
) -> None:
    team = await create_team(rules_client)
    await _set(rules_app, rules_client, team, aging_percentile=60)

    body = (await rules_client.get("/api/metrics/aging-wip", params={"team_id": team})).json()

    assert body["percentile"] == 60


async def test_period_follows_dst_in_the_teams_timezone(
    rules_app: FastAPI, rules_client: AsyncClient
) -> None:
    team = await create_team(rules_client)
    await _set(rules_app, rules_client, team, timezone="America/New_York")

    body = (
        await rules_client.get(
            "/api/metrics", params={"team_id": team, "start": "2026-03-01", "end": "2026-03-31"}
        )
    ).json()

    # EST local midnight at the start, EDT local midnight after the end date.
    assert datetime.fromisoformat(body["window_start"]) == datetime(2026, 3, 1, 5, tzinfo=UTC)
    assert datetime.fromisoformat(body["window_end"]) == datetime(2026, 4, 1, 4, tzinfo=UTC)
