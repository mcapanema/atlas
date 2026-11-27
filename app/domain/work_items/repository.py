from collections.abc import Collection
from typing import Protocol
from uuid import UUID

from app.domain.work_items.entities import Iteration, WorkItem


class WorkItemRepository(Protocol):
    """Port for persisting and retrieving Work Items. Implemented in Infrastructure."""

    async def add(self, work_item: WorkItem) -> None: ...

    async def update(self, work_item: WorkItem) -> None: ...

    async def delete(self, work_item_ids: list[UUID]) -> None:
        """Delete these work items; unknown ids are ignored, their children lose the parent link.

        Delete their events first.
        """
        ...

    async def get_by_keys(
        self, keys: list[str], *, team_ids: Collection[UUID]
    ) -> dict[str, WorkItem]:
        """Items of the given teams by exact source key; unknown keys are absent."""
        ...

    # Must stay above `list` — that method shadows the `list` builtin for every
    # annotation below it in this class body, so `-> list[str]` would fail.
    async def list_states(
        self, *, team_id: UUID | None = None, project_id: UUID | None = None
    ) -> list[str]: ...

    async def list_labels(
        self, *, team_id: UUID | None = None, project_id: UUID | None = None
    ) -> list[str]:
        """Distinct label names in scope, sorted."""
        ...

    async def list_children(
        self, parent_ids: Collection[UUID], also_ids: Collection[UUID]
    ) -> list[WorkItem]:
        """Items, in any team, whose parent is in `parent_ids`, plus the items `also_ids`."""
        ...

    async def team_ids_by_project(self) -> dict[UUID, frozenset[UUID]]:
        """Each project that has items, mapped to the distinct teams of those items."""
        ...

    async def iterations_by_team(self, team_ids: Collection[UUID]) -> dict[UUID, list[Iteration]]:
        """Distinct iterations on the teams' items (any state, archived too), by start.

        A team with no iterated item is absent.
        """
        ...

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
