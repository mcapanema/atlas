from uuid import uuid4

from app.application.work_items.service import WorkItemService
from app.domain.work_items.entities import WorkItem, WorkItemType
from tests.fakes import InMemoryWorkItemRepository


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


async def test_list_states_delegates_to_repository() -> None:
    team_id = uuid4()
    service = WorkItemService(
        InMemoryWorkItemRepository(
            [
                WorkItem(team_id=team_id, title="A", state="done"),
                WorkItem(team_id=team_id, title="B", state="backlog"),
                WorkItem(team_id=uuid4(), title="C", state="archived"),
            ]
        )
    )

    assert await service.list_states(team_id=team_id) == ["backlog", "done"]
