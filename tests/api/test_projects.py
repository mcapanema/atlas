from uuid import uuid4

from httpx import AsyncClient


async def test_list_projects_empty(client: AsyncClient) -> None:
    response = await client.get("/api/projects")

    assert response.status_code == 200
    assert response.json() == []


async def test_create_then_list_project(client: AsyncClient) -> None:
    team_id = str(uuid4())
    create = await client.post(
        "/api/projects", json={"team_id": team_id, "name": "Checkout"}
    )

    assert create.status_code == 201
    body = create.json()
    assert body["name"] == "Checkout"
    assert body["team_id"] == team_id

    listed = await client.get("/api/projects")
    assert [p["name"] for p in listed.json()] == ["Checkout"]


async def test_create_rejects_empty_name(client: AsyncClient) -> None:
    response = await client.post(
        "/api/projects", json={"team_id": str(uuid4()), "name": ""}
    )

    assert response.status_code == 422
