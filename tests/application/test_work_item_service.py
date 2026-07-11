from uuid import UUID, uuid4

from app.application.work_items.service import WorkItemService
from app.domain.work_items.entities import WorkItem, WorkItemType


class InMemoryWorkItemRepository:
    def __init__(self) -> None:
        self._items: dict[UUID, WorkItem] = {}

    async def add(self, work_item: WorkItem) -> None:
        self._items[work_item.id] = work_item

    async def update(self, work_item: WorkItem) -> None:
        self._items[work_item.id] = work_item

    async def list(
        self,
        *,
        team_id: UUID | None = None,
        project_id: UUID | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[WorkItem]:
        items = list(self._items.values())
        if team_id is not None:
            items = [i for i in items if i.team_id == team_id]
        if project_id is not None:
            items = [i for i in items if i.project_id == project_id]
        items = items[offset:]
        return items if limit is None else items[:limit]

    async def count(
        self, *, team_id: UUID | None = None, project_id: UUID | None = None
    ) -> int:
        return len(await self.list(team_id=team_id, project_id=project_id))

    async def get(self, work_item_id: UUID) -> WorkItem | None:
        return self._items.get(work_item_id)

    async def get_by_external_id(self, external_id: str) -> WorkItem | None:
        return next(
            (i for i in self._items.values() if i.external_id == external_id), None
        )


async def test_create_work_item_defaults_to_task() -> None:
    repo = InMemoryWorkItemRepository()
    service = WorkItemService(repo)
    team_id = uuid4()

    item = await service.create_work_item(team_id=team_id, title="Add login")

    assert item.team_id == team_id
    assert item.type is WorkItemType.TASK
    assert await repo.get(item.id) is item


async def test_list_filters_by_team() -> None:
    repo = InMemoryWorkItemRepository()
    service = WorkItemService(repo)
    team_a, team_b = uuid4(), uuid4()
    await service.create_work_item(team_id=team_a, title="A", type=WorkItemType.BUG)
    await service.create_work_item(team_id=team_b, title="B")

    items = await service.list_work_items(team_id=team_a)

    assert [i.title for i in items] == ["A"]
    assert items[0].type is WorkItemType.BUG


async def test_get_work_item_returns_created_item() -> None:
    repo = InMemoryWorkItemRepository()
    service = WorkItemService(repo)
    item = await service.create_work_item(team_id=uuid4(), title="Add login")

    assert await service.get_work_item(item.id) is item


async def test_get_work_item_returns_none_for_unknown_id() -> None:
    service = WorkItemService(InMemoryWorkItemRepository())

    assert await service.get_work_item(uuid4()) is None


async def test_list_paginates_and_counts() -> None:
    repo = InMemoryWorkItemRepository()
    service = WorkItemService(repo)
    team_id = uuid4()
    for title in ["A", "B", "C"]:
        await service.create_work_item(team_id=team_id, title=title)

    page = await service.list_work_items(team_id=team_id, limit=2, offset=1)

    assert [i.title for i in page] == ["B", "C"]
    assert await service.count_work_items(team_id=team_id) == 3
