from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from httpx import AsyncClient


async def _create_team(client: AsyncClient) -> str:
    org = (await client.post("/api/organizations", json={"name": "Acme"})).json()
    team = (
        await client.post(
            "/api/teams", json={"organization_id": org["id"], "name": "Platform"}
        )
    ).json()
    return str(team["id"])


async def test_team_flow_metrics_end_to_end(client: AsyncClient) -> None:
    team_id = await _create_team(client)
    item = (
        await client.post("/api/work-items", json={"team_id": team_id, "title": "Ship"})
    ).json()
    now = datetime.now(UTC)
    for type_, days_ago in (("created", 10), ("started", 6), ("completed", 2)):
        response = await client.post(
            "/api/events",
            json={
                "work_item_id": item["id"],
                "type": type_,
                "occurred_at": (now - timedelta(days=days_ago)).isoformat(),
            },
        )
        assert response.status_code == 201

    response = await client.get(f"/api/metrics?team_id={team_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["completed"] == 1
    assert body["wip"] == 0
    assert body["lead_time"]["p50_seconds"] == pytest.approx(8 * 86400)
    assert body["cycle_time"]["p50_seconds"] == pytest.approx(4 * 86400)
    assert body["blocked_seconds"] == 0
    assert body["flow_efficiency"] == 1.0


async def test_metrics_for_unknown_team_are_empty(client: AsyncClient) -> None:
    response = await client.get(f"/api/metrics?team_id={uuid4()}")

    assert response.status_code == 200
    body = response.json()
    assert body["completed"] == 0
    assert body["wip"] == 0
    assert body["lead_time"] is None
    assert body["cycle_time"] is None
    assert body["flow_efficiency"] is None


async def test_window_days_is_validated(client: AsyncClient) -> None:
    assert (await client.get(f"/api/metrics?team_id={uuid4()}&window_days=0")).status_code == 422
    assert (await client.get("/api/metrics")).status_code == 422  # a scope is required


async def test_metrics_scoped_by_project(client: AsyncClient) -> None:
    team_id = await _create_team(client)
    project = (
        await client.post("/api/projects", json={"team_id": team_id, "name": "Apollo"})
    ).json()
    now = datetime.now(UTC)
    for title, project_id in (("In project", project["id"]), ("Outside", None)):
        item = (
            await client.post(
                "/api/work-items",
                json={"team_id": team_id, "title": title, "project_id": project_id},
            )
        ).json()
        await client.post(
            "/api/events",
            json={
                "work_item_id": item["id"],
                "type": "completed",
                "occurred_at": (now - timedelta(days=1)).isoformat(),
            },
        )

    response = await client.get(f"/api/metrics?project_id={project['id']}")

    assert response.status_code == 200
    assert response.json()["completed"] == 1


async def test_metrics_requires_exactly_one_scope(client: AsyncClient) -> None:
    assert (await client.get("/api/metrics")).status_code == 422
    assert (
        await client.get(f"/api/metrics?team_id={uuid4()}&project_id={uuid4()}")
    ).status_code == 422


async def test_flow_history_end_to_end(client: AsyncClient) -> None:
    team_id = await _create_team(client)
    item = (
        await client.post("/api/work-items", json={"team_id": team_id, "title": "Ship"})
    ).json()
    now = datetime.now(UTC)
    for type_, days_ago in (("created", 10), ("started", 6), ("completed", 2)):
        await client.post(
            "/api/events",
            json={
                "work_item_id": item["id"],
                "type": type_,
                "occurred_at": (now - timedelta(days=days_ago)).isoformat(),
            },
        )

    response = await client.get(f"/api/metrics/history?team_id={team_id}")

    assert response.status_code == 200
    body = response.json()
    assert len(body["days"]) == 91  # default 90-day window, inclusive
    assert body["days"][-1]["done"] == 1
    assert body["days"][-1]["in_progress"] == 0
    assert len(body["weeks"]) == 12
    assert sum(w["completed"] for w in body["weeks"]) == 1


async def test_flow_history_requires_exactly_one_scope(client: AsyncClient) -> None:
    assert (await client.get("/api/metrics/history")).status_code == 422
    assert (
        await client.get(f"/api/metrics/history?team_id={uuid4()}&project_id={uuid4()}")
    ).status_code == 422
