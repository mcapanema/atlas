from uuid import uuid4

from httpx import AsyncClient


async def test_list_work_items_empty(client: AsyncClient) -> None:
    response = await client.get("/api/work-items")

    assert response.status_code == 200
    assert response.json() == []


async def test_create_then_list_work_item(client: AsyncClient) -> None:
    team_id = str(uuid4())
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
    team_a, team_b = str(uuid4()), str(uuid4())
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
