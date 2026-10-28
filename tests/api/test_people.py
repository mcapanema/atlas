from uuid import UUID, uuid4

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.people.entities import Person
from app.infrastructure.repositories.people import SqlAlchemyPersonRepository


async def store_person(
    sessionmaker: async_sessionmaker[AsyncSession], name: str = "Joao", org_id: UUID | None = None
) -> Person:
    person = Person(organization_id=org_id or uuid4(), name=name, email="j@x.com")
    async with sessionmaker() as session:
        await SqlAlchemyPersonRepository(session).add(person)
        await session.commit()
    return person


async def test_list_people_returns_shown_name(
    client: AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    org_id = uuid4()
    person = await store_person(sessionmaker, org_id=org_id)
    await store_person(sessionmaker, name="Other")

    body = (await client.get(f"/api/people?organization_id={org_id}")).json()

    assert body == [
        {
            "id": str(person.id),
            "organization_id": str(org_id),
            "name": "Joao",
            "display_name": None,
            "shown_name": "Joao",
            "email": "j@x.com",
        }
    ]


async def test_patch_display_name_sets_override(
    client: AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    person = await store_person(sessionmaker)

    response = await client.patch(f"/api/people/{person.id}", json={"display_name": "João"})

    assert response.status_code == 200
    assert response.json()["display_name"] == "João"
    assert response.json()["shown_name"] == "João"
    assert response.json()["name"] == "Joao"


async def test_patch_blank_display_name_clears_override(
    client: AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    person = await store_person(sessionmaker)
    await client.patch(f"/api/people/{person.id}", json={"display_name": "João"})

    response = await client.patch(f"/api/people/{person.id}", json={"display_name": "  "})

    assert response.status_code == 200
    assert response.json()["display_name"] is None
    assert response.json()["shown_name"] == "Joao"


async def test_patch_unknown_person_is_404(client: AsyncClient) -> None:
    response = await client.patch(f"/api/people/{uuid4()}", json={"display_name": "X"})
    assert response.status_code == 404


async def test_patch_too_long_display_name_is_422(
    client: AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    person = await store_person(sessionmaker)

    response = await client.patch(f"/api/people/{person.id}", json={"display_name": "x" * 256})

    assert response.status_code == 422
