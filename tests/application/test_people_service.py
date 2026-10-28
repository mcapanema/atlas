from uuid import uuid4

import pytest

from app.application.people.service import PeopleService, UnknownPersonError
from app.domain.people.entities import Person
from tests.fakes import InMemoryPersonRepository


async def test_set_display_name_updates_only_the_override() -> None:
    person = Person(organization_id=uuid4(), name="Joao", external_id="u1", email="j@x.com")
    repo = InMemoryPersonRepository([person])

    updated = await PeopleService(repo).set_display_name(person.id, "João")

    assert updated.display_name == "João"
    assert updated.shown_name == "João"
    stored = await repo.get(person.id)
    assert stored is not None
    assert (stored.name, stored.external_id, stored.email) == ("Joao", "u1", "j@x.com")


async def test_unknown_person_raises() -> None:
    with pytest.raises(UnknownPersonError):
        await PeopleService(InMemoryPersonRepository()).set_display_name(uuid4(), "X")
