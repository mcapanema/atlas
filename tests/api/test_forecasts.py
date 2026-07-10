from datetime import UTC, datetime, timedelta
from uuid import uuid4

from httpx import AsyncClient


async def _create_team(client: AsyncClient) -> str:
    org = (await client.post("/api/organizations", json={"name": "Acme"})).json()
    team = (
        await client.post(
            "/api/teams", json={"organization_id": org["id"], "name": "Platform"}
        )
    ).json()
    return str(team["id"])


async def _seed_history(client: AsyncClient, team_id: str) -> None:
    """Three completed items on recent distinct days, plus one open item."""
    now = datetime.now(UTC)
    for days_ago in (1, 2, 3):
        item = (
            await client.post(
                "/api/work-items", json={"team_id": team_id, "title": f"Done {days_ago}"}
            )
        ).json()
        response = await client.post(
            "/api/events",
            json={
                "work_item_id": item["id"],
                "type": "completed",
                "occurred_at": (now - timedelta(days=days_ago)).isoformat(),
            },
        )
        assert response.status_code == 201
    await client.post("/api/work-items", json={"team_id": team_id, "title": "Open"})


async def test_forecast_end_to_end(client: AsyncClient) -> None:
    team_id = await _create_team(client)
    await _seed_history(client, team_id)

    response = await client.get(f"/api/forecasts?team_id={team_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["remaining"] == 1
    assert body["confidence"] is None
    completion = body["completion"]
    assert completion is not None
    assert completion["trials"] == 2000
    assert len(completion["outcomes"]) >= 1
    assert completion["p50_date"] > body["window_end"]


async def test_forecast_confidence_with_target_date(client: AsyncClient) -> None:
    team_id = await _create_team(client)
    await _seed_history(client, team_id)
    target = (datetime.now(UTC) + timedelta(days=365)).date().isoformat()

    response = await client.get(f"/api/forecasts?team_id={team_id}&target_date={target}")

    assert response.status_code == 200
    confidence = response.json()["confidence"]
    assert confidence is not None
    assert 0.0 <= confidence <= 1.0


async def test_forecast_is_deterministic_across_requests(client: AsyncClient) -> None:
    team_id = await _create_team(client)
    await _seed_history(client, team_id)

    first = (await client.get(f"/api/forecasts?team_id={team_id}")).json()
    second = (await client.get(f"/api/forecasts?team_id={team_id}")).json()

    assert first["completion"]["outcomes"] == second["completion"]["outcomes"]


async def test_forecast_without_history_has_no_completion(client: AsyncClient) -> None:
    team_id = await _create_team(client)
    await client.post("/api/work-items", json={"team_id": team_id, "title": "Open"})

    response = await client.get(f"/api/forecasts?team_id={team_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["remaining"] == 1
    assert body["completion"] is None
    assert body["confidence"] is None


async def test_forecast_requires_exactly_one_scope(client: AsyncClient) -> None:
    assert (await client.get("/api/forecasts")).status_code == 422
    assert (
        await client.get(f"/api/forecasts?team_id={uuid4()}&project_id={uuid4()}")
    ).status_code == 422


async def test_forecast_validates_query_params(client: AsyncClient) -> None:
    team_id = await _create_team(client)
    assert (
        await client.get(f"/api/forecasts?team_id={team_id}&window_days=1")
    ).status_code == 422
    assert (
        await client.get(f"/api/forecasts?team_id={team_id}&remaining=-1")
    ).status_code == 422


async def test_forecast_for_unknown_team_is_404(client: AsyncClient) -> None:
    response = await client.get(f"/api/forecasts?team_id={uuid4()}")

    assert response.status_code == 404
