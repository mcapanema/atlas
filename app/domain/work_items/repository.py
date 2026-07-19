from typing import Protocol
from uuid import UUID

from app.domain.work_items.entities import WorkItem


class WorkItemRepository(Protocol):
    """Port for persisting and retrieving Work Items. Implemented in Infrastructure."""

    async def add(self, work_item: WorkItem) -> None: ...

    async def update(self, work_item: WorkItem) -> None: ...

    # Must stay above `list` — that method shadows the `list` builtin for every
    # annotation below it in this class body, so `-> list[str]` would fail.
    async def list_states(
        self, *, team_id: UUID | None = None, project_id: UUID | None = None
    ) -> list[str]: ...

    async def list(
        self,
        *,
        team_id: UUID | None = None,
        project_id: UUID | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[WorkItem]: ...

    async def count(
        self, *, team_id: UUID | None = None, project_id: UUID | None = None
    ) -> int: ...

    async def get(self, work_item_id: UUID) -> WorkItem | None: ...

    async def get_by_external_id(self, external_id: str) -> WorkItem | None: ...
