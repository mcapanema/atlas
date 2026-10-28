from collections.abc import Collection
from typing import Protocol
from uuid import UUID

from app.domain.people.entities import Person


class PersonRepository(Protocol):
    """Port for persisting and retrieving People. Implemented in Infrastructure."""

    async def add(self, person: Person) -> None: ...

    async def update(self, person: Person) -> None: ...

    async def get(self, person_id: UUID) -> Person | None: ...

    async def list(self, organization_id: UUID | None = None) -> list[Person]:
        """Ordered by shown name, case-insensitive."""
        ...

    async def get_by_external_ids(self, external_ids: Collection[str]) -> dict[str, Person]: ...
