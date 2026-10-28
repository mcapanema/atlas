from uuid import uuid4

from httpx import AsyncClient

from tests.api.helpers import create_org_and_team, create_team


async def test_list_projects_empty(client: AsyncClient) -> None:
    response = await client.get("/api/projects")

    assert response.status_code == 200
    assert response.json() == []


async def test_create_then_list_project(client: AsyncClient) -> None:
    team_id = await create_team(client)
    create = await client.post("/api/projects", json={"team_id": team_id, "name": "Checkout"})

    assert create.status_code == 201
    body = create.json()
    assert body["name"] == "Checkout"
    assert body["team_id"] == team_id

    listed = await client.get("/api/projects")
    assert [p["name"] for p in listed.json()] == ["Checkout"]


async def test_create_rejects_empty_name(client: AsyncClient) -> None:
    response = await client.post("/api/projects", json={"team_id": str(uuid4()), "name": ""})

    assert response.status_code == 422


async def test_create_project_404_for_unknown_team(client: AsyncClient) -> None:
    response = await client.post(
        "/api/projects", json={"team_id": str(uuid4()), "name": "Checkout"}
    )

    assert response.status_code == 404


async def test_list_projects_includes_every_team(client: AsyncClient) -> None:
    org_id, home = await create_org_and_team(client)
    other = (
        await client.post("/api/teams", json={"organization_id": org_id, "name": "Mobile"})
    ).json()["id"]
    project = (await client.post("/api/projects", json={"team_id": home, "name": "Apollo"})).json()
    assert project["team_ids"] == [home]
    for team_id in (other, home):
        await client.post(
            "/api/work-items", json={"team_id": team_id, "title": "x", "project_id": project["id"]}
        )

    listed = (await client.get("/api/projects")).json()

    assert listed[0]["team_id"] == home
    assert listed[0]["team_ids"] == [home, other]
