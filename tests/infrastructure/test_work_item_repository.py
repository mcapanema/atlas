from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.work_items.entities import WorkItem, WorkItemType
from app.infrastructure.repositories.work_items import SqlAlchemyWorkItemRepository


async def test_add_then_get_roundtrips_enum(session: AsyncSession) -> None:
    repo = SqlAlchemyWorkItemRepository(session)
    item = WorkItem(
        team_id=uuid4(), title="Add login", type=WorkItemType.BUG, state="in_progress"
    )

    await repo.add(item)
    fetched = await repo.get(item.id)

    assert fetched is not None
    assert fetched.title == "Add login"
    assert fetched.type is WorkItemType.BUG
    assert fetched.state == "in_progress"


async def test_get_by_external_id(session: AsyncSession) -> None:
    repo = SqlAlchemyWorkItemRepository(session)
    item = WorkItem(team_id=uuid4(), title="Add login", external_id="lin_i1")
    await repo.add(item)

    fetched = await repo.get_by_external_id("lin_i1")

    assert fetched is not None and fetched.id == item.id
    assert await repo.get_by_external_id("nope") is None


async def test_list_filters_by_team_and_project(session: AsyncSession) -> None:
    repo = SqlAlchemyWorkItemRepository(session)
    team_a, team_b, project = uuid4(), uuid4(), uuid4()
    await repo.add(WorkItem(team_id=team_a, title="A", project_id=project))
    await repo.add(WorkItem(team_id=team_a, title="B"))
    await repo.add(WorkItem(team_id=team_b, title="C"))

    assert {i.title for i in await repo.list(team_id=team_a)} == {"A", "B"}
    assert {i.title for i in await repo.list(project_id=project)} == {"A"}
    assert {i.title for i in await repo.list()} == {"A", "B", "C"}
