from uuid import UUID, uuid4

from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.deps import get_codebase_service
from app.domain.codebases.entities import Codebase
from app.infrastructure.repositories.codebases import SqlAlchemyCodebaseRepository
from tests.api.helpers import create_org_and_team


async def _seed_codebase(
    sessionmaker: async_sessionmaker[AsyncSession], organization_id: str
) -> str:
    codebase = Codebase(
        organization_id=UUID(organization_id),
        name="atlas",
        external_id="r1",
        url="https://example.test/acme/atlas",
    )
    async with sessionmaker() as session:
        await SqlAlchemyCodebaseRepository(session).add(codebase)
        await session.commit()
    return str(codebase.id)


async def test_get_lists_the_organizations_codebases(
    client: AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    org_id, _ = await create_org_and_team(client)
    codebase_id = await _seed_codebase(sessionmaker, org_id)

    response = await client.get(f"/api/codebases?organization_id={org_id}")

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": codebase_id,
            "organization_id": org_id,
            "name": "atlas",
            "url": "https://example.test/acme/atlas",
            "team_id": None,
            "production_environment": "production",
            "last_synced_at": None,
            "pull_requests": 0,
            "deployments": 0,
        }
    ]


async def test_put_maps_codebase_to_team(
    client: AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    org_id, team_id = await create_org_and_team(client)
    codebase_id = await _seed_codebase(sessionmaker, org_id)

    response = await client.put(
        f"/api/codebases/{codebase_id}",
        json={"team_id": team_id, "production_environment": "prod"},
    )

    assert response.status_code == 200
    body = response.json()
    assert (body["id"], body["team_id"], body["production_environment"]) == (
        codebase_id,
        team_id,
        "prod",
    )
    assert body["pull_requests"] == 0
    listed = (await client.get(f"/api/codebases?organization_id={org_id}")).json()
    assert listed[0]["team_id"] == team_id


async def test_put_unknown_codebase_answers_404(client: AsyncClient) -> None:
    response = await client.put(
        f"/api/codebases/{uuid4()}",
        json={"team_id": None, "production_environment": "production"},
    )

    assert response.status_code == 404


async def test_put_blank_environment_answers_422(
    client: AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    org_id, team_id = await create_org_and_team(client)
    codebase_id = await _seed_codebase(sessionmaker, org_id)

    empty = await client.put(
        f"/api/codebases/{codebase_id}",
        json={"team_id": team_id, "production_environment": ""},
    )
    blank = await client.put(
        f"/api/codebases/{codebase_id}",
        json={"team_id": team_id, "production_environment": "   "},
    )

    assert (empty.status_code, blank.status_code) == (422, 422)


async def test_put_team_of_another_organization_answers_422(
    client: AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    org_id, _ = await create_org_and_team(client)
    _, other_team = await create_org_and_team(client)
    codebase_id = await _seed_codebase(sessionmaker, org_id)

    response = await client.put(
        f"/api/codebases/{codebase_id}",
        json={"team_id": other_team, "production_environment": "production"},
    )

    assert response.status_code == 422


class _VanishingCodebaseService:
    """Updates a codebase, then lists none: the row went away in between."""

    async def update(
        self, codebase_id: UUID, *, team_id: UUID | None, production_environment: str
    ) -> Codebase:
        return Codebase(organization_id=uuid4(), name="atlas", external_id="r1", id=codebase_id)

    async def list(self, organization_id: UUID) -> list[object]:
        return []


async def test_put_answers_404_when_the_updated_codebase_is_gone(
    client: AsyncClient, test_app: FastAPI
) -> None:
    test_app.dependency_overrides[get_codebase_service] = _VanishingCodebaseService
    codebase_id = uuid4()

    response = await client.put(
        f"/api/codebases/{codebase_id}", json={"team_id": None, "production_environment": "prod"}
    )

    assert response.status_code == 404
    assert response.json()["detail"] == f"Codebase {codebase_id} does not exist"
