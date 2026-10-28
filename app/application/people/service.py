from uuid import UUID

from app.domain.people.entities import Person
from app.domain.people.repository import PersonRepository


class UnknownPersonError(Exception):
    """The person to update does not exist."""


class PeopleService:
    """Application use cases for People."""

    def __init__(self, people: PersonRepository) -> None:
        self._people = people

    async def list(self, organization_id: UUID | None = None) -> list[Person]:
        return await self._people.list(organization_id)

    async def set_display_name(self, person_id: UUID, display_name: str | None) -> Person:
        person = await self._people.get(person_id)
        if person is None:
            raise UnknownPersonError(f"Person {person_id} does not exist")
        person.display_name = display_name
        person.__post_init__()  # a blank override normalises to None
        await self._people.update(person)
        return person
