from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.people.entities import Person
from app.infrastructure.repositories.people import SqlAlchemyPersonRepository


async def test_person_roundtrips(session: AsyncSession) -> None:
    repo = SqlAlchemyPersonRepository(session)
    person = Person(
        organization_id=uuid4(),
        name="Ada Lovelace",
        external_id="u1",
        email="ada@example.com",
        display_name="Ada L.",
    )

    await repo.add(person)
    session.expire_all()

    assert await repo.get(person.id) == person


async def test_update_persists_changes(session: AsyncSession) -> None:
    repo = SqlAlchemyPersonRepository(session)
    person = Person(organization_id=uuid4(), name="Ada")
    await repo.add(person)

    person.display_name = "Ada Lovelace"
    await repo.update(person)
    session.expire_all()
    fetched = await repo.get(person.id)

    assert fetched is not None
    assert fetched.display_name == "Ada Lovelace"


async def test_get_by_external_ids_returns_only_known(session: AsyncSession) -> None:
    repo = SqlAlchemyPersonRepository(session)
    known = Person(organization_id=uuid4(), name="Ada", external_id="u1")
    await repo.add(known)
    await repo.add(Person(organization_id=uuid4(), name="Grace", external_id="u2"))
    await repo.add(Person(organization_id=uuid4(), name="Local"))

    assert await repo.get_by_external_ids(["u1", "missing"]) == {"u1": known}
    assert await repo.get_by_external_ids([]) == {}


async def test_list_orders_by_shown_name_and_filters_by_organization(
    session: AsyncSession,
) -> None:
    repo = SqlAlchemyPersonRepository(session)
    org, other = uuid4(), uuid4()
    zed = Person(organization_id=org, name="zed")
    bea = Person(organization_id=org, name="Zzz", display_name="bea")
    carl = Person(organization_id=org, name="Carl")
    elsewhere = Person(organization_id=other, name="Ann")
    for person in (zed, bea, carl, elsewhere):
        await repo.add(person)

    assert [p.shown_name for p in await repo.list(org)] == ["bea", "Carl", "zed"]
    assert [p.shown_name for p in await repo.list()] == ["Ann", "bea", "Carl", "zed"]
