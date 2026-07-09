from uuid import uuid4

from httpx import AsyncClient


async def test_list_teams_empty(client: AsyncClient) -> None:
    response = await client.get("/api/teams")

    assert response.status_code == 200
    assert response.json() == []


async def test_create_then_list_team(client: AsyncClient) -> None:
    org_id = str(uuid4())
    create = await client.post(
        "/api/teams", json={"organization_id": org_id, "name": "Platform"}
    )

    assert create.status_code == 201
    body = create.json()
    assert body["name"] == "Platform"
    assert body["organization_id"] == org_id
    assert body["external_id"] is None
    assert "id" in body and "created_at" in body

    listed = await client.get("/api/teams")
    assert [t["name"] for t in listed.json()] == ["Platform"]


async def test_create_rejects_empty_name(client: AsyncClient) -> None:
    response = await client.post(
        "/api/teams", json={"organization_id": str(uuid4()), "name": ""}
    )

    assert response.status_code == 422
