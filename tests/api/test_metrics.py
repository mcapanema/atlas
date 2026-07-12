from uuid import uuid4

import pytest
from httpx import AsyncClient

from tests.api.helpers import create_team, days_ago


async def test_team_flow_metrics_end_to_end(client: AsyncClient) -> None:
    team_id = await create_team(client)
    item = (
        await client.post("/api/work-items", json={"team_id": team_id, "title": "Ship"})
    ).json()
    for type_, days in (("created", 10), ("started", 6), ("completed", 2)):
        response = await client.post(
            "/api/events",
            json={
                "work_item_id": item["id"],
                "type": type_,
                "occurred_at": days_ago(days),
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


async def test_metrics_for_unknown_team_is_404(client: AsyncClient) -> None:
    response = await client.get(f"/api/metrics?team_id={uuid4()}")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"]


async def test_metrics_for_unknown_project_is_404(client: AsyncClient) -> None:
    response = await client.get(f"/api/metrics?project_id={uuid4()}")

    assert response.status_code == 404


async def test_flow_history_for_unknown_team_is_404(client: AsyncClient) -> None:
    response = await client.get(f"/api/metrics/history?team_id={uuid4()}")

    assert response.status_code == 404


async def test_window_days_is_validated(client: AsyncClient) -> None:
    team_id = await create_team(client)
    response = await client.get(f"/api/metrics?team_id={team_id}&window_days=0")
    assert response.status_code == 422
    assert (await client.get("/api/metrics")).status_code == 422  # a scope is required


async def test_metrics_scoped_by_project(client: AsyncClient) -> None:
    team_id = await create_team(client)
    project = (
        await client.post("/api/projects", json={"team_id": team_id, "name": "Apollo"})
    ).json()
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
                "occurred_at": days_ago(1),
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
    team_id = await create_team(client)
    item = (
        await client.post("/api/work-items", json={"team_id": team_id, "title": "Ship"})
    ).json()
    for type_, days in (("created", 10), ("started", 6), ("completed", 2)):
        await client.post(
            "/api/events",
            json={
                "work_item_id": item["id"],
                "type": type_,
                "occurred_at": days_ago(days),
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


async def test_lead_time_distribution_end_to_end(client: AsyncClient) -> None:
    team_id = await create_team(client)
    item = (
        await client.post("/api/work-items", json={"team_id": team_id, "title": "Ship"})
    ).json()
    for type_, days in (("created", 10), ("completed", 2)):
        await client.post(
            "/api/events",
            json={
                "work_item_id": item["id"],
                "type": type_,
                "occurred_at": days_ago(days),
            },
        )

    response = await client.get(f"/api/metrics/lead-time-distribution?team_id={team_id}")

    assert response.status_code == 200
    body = response.json()
    assert len(body["bins"]) == 9  # bins for days 0..8
    assert body["bins"][8] == {"start_days": 8, "end_days": 9, "count": 1}
    assert sum(b["count"] for b in body["bins"]) == 1


async def test_lead_time_distribution_requires_exactly_one_scope(client: AsyncClient) -> None:
    assert (await client.get("/api/metrics/lead-time-distribution")).status_code == 422
    assert (
        await client.get(
            f"/api/metrics/lead-time-distribution?team_id={uuid4()}&project_id={uuid4()}"
        )
    ).status_code == 422


async def test_flow_metrics_include_queue_and_touch_time(client: AsyncClient) -> None:
    team_id = await create_team(client)
    item = (
        await client.post("/api/work-items", json={"team_id": team_id, "title": "Ship"})
    ).json()
    for type_, days in (("created", 10), ("started", 6), ("completed", 2)):
        await client.post(
            "/api/events",
            json={"work_item_id": item["id"], "type": type_, "occurred_at": days_ago(days)},
        )

    body = (await client.get(f"/api/metrics?team_id={team_id}")).json()

    assert body["queue_time"]["p50_seconds"] == pytest.approx(4 * 86400)
    assert body["touch_time"]["p50_seconds"] == pytest.approx(4 * 86400)


async def test_aging_wip_end_to_end(client: AsyncClient) -> None:
    team_id = await create_team(client)
    item = (
        await client.post("/api/work-items", json={"team_id": team_id, "title": "Stuck"})
    ).json()
    for type_, days in (("created", 10), ("started", 6)):
        await client.post(
            "/api/events",
            json={"work_item_id": item["id"], "type": type_, "occurred_at": days_ago(days)},
        )

    response = await client.get(f"/api/metrics/aging-wip?team_id={team_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["cycle_time_p85_seconds"] is None
    (aging_item,) = body["items"]
    assert aging_item["title"] == "Stuck"
    assert aging_item["over_p85"] is False
    assert aging_item["age_seconds"] > 5 * 86400


async def test_aging_wip_for_unknown_team_is_404(client: AsyncClient) -> None:
    response = await client.get(f"/api/metrics/aging-wip?team_id={uuid4()}")
    assert response.status_code == 404


async def test_aging_wip_requires_exactly_one_scope(client: AsyncClient) -> None:
    assert (await client.get("/api/metrics/aging-wip")).status_code == 422


async def test_delivery_health_end_to_end(client: AsyncClient) -> None:
    team_id = await create_team(client)
    item = (
        await client.post("/api/work-items", json={"team_id": team_id, "title": "Ship"})
    ).json()
    for type_, days in (("created", 10), ("started", 6), ("completed", 2)):
        await client.post(
            "/api/events",
            json={"work_item_id": item["id"], "type": type_, "occurred_at": days_ago(days)},
        )

    response = await client.get(f"/api/metrics/health?team_id={team_id}")

    assert response.status_code == 200
    body = response.json()
    assert 0 <= body["score"] <= 100
    assert body["band"] in ("healthy", "warning", "critical")
    assert "predictability" in [c["name"] for c in body["components"]]


async def test_delivery_health_for_unknown_team_is_404(client: AsyncClient) -> None:
    assert (await client.get(f"/api/metrics/health?team_id={uuid4()}")).status_code == 404


async def test_delivery_health_requires_exactly_one_scope(client: AsyncClient) -> None:
    assert (await client.get("/api/metrics/health")).status_code == 422
