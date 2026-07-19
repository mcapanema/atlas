from uuid import UUID

from app.domain.work_items.entities import DEFAULT_STATE, WorkItem, WorkItemType
from app.domain.work_items.repository import WorkItemRepository


class WorkItemService:
    """Application use cases for Work Items."""

    def __init__(self, repository: WorkItemRepository) -> None:
        self._repository = repository

    async def create_work_item(
        self,
        team_id: UUID,
        title: str,
        type: WorkItemType = WorkItemType.TASK,
        state: str = DEFAULT_STATE,
        project_id: UUID | None = None,
        external_id: str | None = None,
    ) -> WorkItem:
        work_item = WorkItem(
            team_id=team_id,
            title=title,
            type=type,
            state=state,
            project_id=project_id,
            external_id=external_id,
        )
        await self._repository.add(work_item)
        return work_item

    async def list_work_items(
        self,
        *,
        team_id: UUID | None = None,
        project_id: UUID | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[WorkItem]:
        return await self._repository.list(
            team_id=team_id, project_id=project_id, limit=limit, offset=offset
        )

    async def count_work_items(
        self, *, team_id: UUID | None = None, project_id: UUID | None = None
    ) -> int:
        return await self._repository.count(team_id=team_id, project_id=project_id)

    async def list_states(
        self, *, team_id: UUID | None = None, project_id: UUID | None = None
    ) -> list[str]:
        return await self._repository.list_states(team_id=team_id, project_id=project_id)

    async def get_work_item(self, work_item_id: UUID) -> WorkItem | None:
        return await self._repository.get(work_item_id)
