from collections.abc import Mapping
from typing import Protocol
from uuid import UUID

from app.domain.events.entities import Event
from app.domain.work_items.entities import StateType


class EventRepository(Protocol):
    """Port for persisting and retrieving Events. Implemented in Infrastructure."""

    async def add(self, event: Event) -> None: ...

    async def delete_for_work_items(self, work_item_ids: list[UUID]) -> None: ...

    async def list_for_work_item(self, work_item_id: UUID) -> list[Event]: ...

    async def list_for_work_items(self, work_item_ids: list[UUID]) -> list[Event]: ...

    async def get_by_external_id(self, external_id: str) -> Event | None: ...

    async def existing_external_ids(self, external_ids: list[str]) -> set[str]: ...

    async def external_ids_missing_state_types(self, external_ids: list[str]) -> set[str]:
        """Stored events among `external_ids` whose state types are still unknown."""
        ...

    async def fill_state_types(
        self, types_by_external_id: Mapping[str, tuple[StateType | None, StateType | None]]
    ) -> int:
        """Set (from, to) state types on stored events whose types are unknown; never overwrite.

        The one exception to insert-only events (ADR-0011). Returns rows changed.
        """
        ...
