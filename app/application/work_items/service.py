from uuid import UUID

from app.domain.work_items.entities import WorkItem, WorkItemType
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
        state: str = "backlog",
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
        self, *, team_id: UUID | None = None, project_id: UUID | None = None
    ) -> list[WorkItem]:
        return await self._repository.list(team_id=team_id, project_id=project_id)
