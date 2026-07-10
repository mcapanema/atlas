from typing import Protocol
from uuid import UUID

from app.domain.events.entities import Event


class EventRepository(Protocol):
    """Port for persisting and retrieving Events. Implemented in Infrastructure."""

    async def add(self, event: Event) -> None: ...

    async def list_for_work_item(self, work_item_id: UUID) -> list[Event]: ...

    async def list_for_work_items(self, work_item_ids: list[UUID]) -> list[Event]: ...

    async def get_by_external_id(self, external_id: str) -> Event | None: ...
