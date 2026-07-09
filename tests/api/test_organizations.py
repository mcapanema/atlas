from httpx import AsyncClient


async def test_list_organizations_empty(client: AsyncClient) -> None:
    response = await client.get("/api/organizations")

    assert response.status_code == 200
    assert response.json() == []


async def test_create_then_list_organization(client: AsyncClient) -> None:
    create = await client.post("/api/organizations", json={"name": "Acme"})

    assert create.status_code == 201
    body = create.json()
    assert body["name"] == "Acme"
    assert "id" in body and "created_at" in body

    listed = await client.get("/api/organizations")
    assert [o["name"] for o in listed.json()] == ["Acme"]


async def test_create_rejects_empty_name(client: AsyncClient) -> None:
    response = await client.post("/api/organizations", json={"name": ""})

    assert response.status_code == 422
