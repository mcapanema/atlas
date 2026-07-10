from uuid import uuid4

from httpx import AsyncClient

from tests.api.helpers import create_team, create_work_item


async def test_list_work_items_empty(client: AsyncClient) -> None:
    response = await client.get("/api/work-items")

    assert response.status_code == 200
    assert response.json() == []


async def test_create_then_list_work_item(client: AsyncClient) -> None:
    team_id = await create_team(client)
    create = await client.post(
        "/api/work-items",
        json={"team_id": team_id, "title": "Add login", "type": "bug"},
    )

    assert create.status_code == 201
    body = create.json()
    assert body["title"] == "Add login"
    assert body["type"] == "bug"
    assert body["state"] == "backlog"
    assert body["project_id"] is None

    listed = await client.get("/api/work-items")
    assert [i["title"] for i in listed.json()] == ["Add login"]


async def test_list_filters_by_team(client: AsyncClient) -> None:
    team_a, team_b = await create_team(client), await create_team(client)
    await client.post("/api/work-items", json={"team_id": team_a, "title": "A"})
    await client.post("/api/work-items", json={"team_id": team_b, "title": "B"})

    response = await client.get("/api/work-items", params={"team_id": team_a})

    assert [i["title"] for i in response.json()] == ["A"]


async def test_create_rejects_empty_title(client: AsyncClient) -> None:
    response = await client.post(
        "/api/work-items", json={"team_id": str(uuid4()), "title": ""}
    )

    assert response.status_code == 422


async def test_create_rejects_unknown_type(client: AsyncClient) -> None:
    response = await client.post(
        "/api/work-items",
        json={"team_id": str(uuid4()), "title": "X", "type": "epic"},
    )

    assert response.status_code == 422


async def test_create_work_item_404_for_unknown_team(client: AsyncClient) -> None:
    response = await client.post(
        "/api/work-items", json={"team_id": str(uuid4()), "title": "X"}
    )

    assert response.status_code == 404


async def test_create_work_item_404_for_unknown_project(client: AsyncClient) -> None:
    team_id = await create_team(client)
    response = await client.post(
        "/api/work-items",
        json={"team_id": team_id, "title": "X", "project_id": str(uuid4())},
    )

    assert response.status_code == 404


async def test_get_work_item_by_id(client: AsyncClient) -> None:
    work_item_id = await create_work_item(client)

    response = await client.get(f"/api/work-items/{work_item_id}")

    assert response.status_code == 200
    assert response.json()["title"] == "Ship it"


async def test_get_work_item_404_for_unknown_id(client: AsyncClient) -> None:
    response = await client.get(f"/api/work-items/{uuid4()}")

    assert response.status_code == 404


async def test_timeline_derives_periods_from_events(client: AsyncClient) -> None:
    work_item_id = await create_work_item(client)
    for payload in [
        {"type": "created", "occurred_at": "2026-01-01T00:00:00Z"},
        {
            "type": "started",
            "occurred_at": "2026-01-03T00:00:00Z",
            "from_state": "Backlog",
            "to_state": "In Progress",
        },
        {"type": "blocked", "occurred_at": "2026-01-04T00:00:00Z"},
        {"type": "unblocked", "occurred_at": "2026-01-05T00:00:00Z"},
    ]:
        created = await client.post(
            "/api/events", json={"work_item_id": work_item_id, **payload}
        )
        assert created.status_code == 201

    response = await client.get(f"/api/work-items/{work_item_id}/timeline")

    assert response.status_code == 200
    body = response.json()
    assert [p["state"] for p in body["state_periods"]] == ["Backlog", "In Progress"]
    assert body["state_periods"][0]["exited_at"] == "2026-01-03T00:00:00Z"
    assert body["state_periods"][1]["exited_at"] is None
    assert body["blocked_periods"] == [
        {"started_at": "2026-01-04T00:00:00Z", "ended_at": "2026-01-05T00:00:00Z"}
    ]


async def test_timeline_404_for_unknown_work_item(client: AsyncClient) -> None:
    response = await client.get(f"/api/work-items/{uuid4()}/timeline")

    assert response.status_code == 404
