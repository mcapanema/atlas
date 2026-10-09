from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.projects.entities import Project
from app.domain.teams.entities import Team
from app.domain.work_items.entities import StateType, WorkItem, WorkItemType
from app.infrastructure.repositories.projects import SqlAlchemyProjectRepository
from app.infrastructure.repositories.teams import SqlAlchemyTeamRepository
from app.infrastructure.repositories.work_items import SqlAlchemyWorkItemRepository


async def _team_id(session: AsyncSession) -> UUID:
    """FK enforcement is on (see conftest) — work items need a real team."""
    team = Team(organization_id=uuid4(), name="Platform")
    await SqlAlchemyTeamRepository(session).add(team)
    return team.id


async def _project_id(session: AsyncSession, team_id: UUID) -> UUID:
    project = Project(team_id=team_id, name="Checkout")
    await SqlAlchemyProjectRepository(session).add(project)
    return project.id


async def test_add_then_get_roundtrips_enum(session: AsyncSession) -> None:
    repo = SqlAlchemyWorkItemRepository(session)
    item = WorkItem(
        team_id=await _team_id(session),
        title="Add login",
        type=WorkItemType.BUG,
        state="in_progress",
    )

    await repo.add(item)
    fetched = await repo.get(item.id)

    assert fetched is not None
    assert fetched.title == "Add login"
    assert fetched.type is WorkItemType.BUG
    assert fetched.state == "in_progress"


async def test_get_by_external_id(session: AsyncSession) -> None:
    repo = SqlAlchemyWorkItemRepository(session)
    item = WorkItem(team_id=await _team_id(session), title="Add login", external_id="lin_i1")
    await repo.add(item)

    fetched = await repo.get_by_external_id("lin_i1")

    assert fetched is not None
    assert fetched.id == item.id
    assert await repo.get_by_external_id("nope") is None


async def test_list_filters_by_team_and_project(session: AsyncSession) -> None:
    repo = SqlAlchemyWorkItemRepository(session)
    team_a, team_b = await _team_id(session), await _team_id(session)
    project = await _project_id(session, team_a)
    await repo.add(WorkItem(team_id=team_a, title="A", project_id=project))
    await repo.add(WorkItem(team_id=team_a, title="B"))
    await repo.add(WorkItem(team_id=team_b, title="C"))

    assert {i.title for i in await repo.list(team_id=team_a)} == {"A", "B"}
    assert {i.title for i in await repo.list(project_id=project)} == {"A"}
    assert {i.title for i in await repo.list()} == {"A", "B", "C"}


async def test_update_persists_changed_fields(session: AsyncSession) -> None:
    repo = SqlAlchemyWorkItemRepository(session)
    team_id = await _team_id(session)
    item = WorkItem(team_id=team_id, title="Add login", state="backlog")
    await repo.add(item)

    new_project_id = await _project_id(session, team_id)
    item.state = "In Progress"
    item.project_id = new_project_id
    await repo.update(item)

    fetched = await repo.get(item.id)
    assert fetched is not None
    assert fetched.state == "In Progress"
    assert fetched.project_id == new_project_id


async def test_list_paginates_in_created_order(session: AsyncSession) -> None:
    repo = SqlAlchemyWorkItemRepository(session)
    team_id = await _team_id(session)
    for day, title in [(3, "C"), (1, "A"), (2, "B")]:
        await repo.add(
            WorkItem(
                team_id=team_id,
                title=title,
                created_at=datetime(2026, 7, day, tzinfo=UTC),
            )
        )

    page = await repo.list(team_id=team_id, limit=2, offset=1)

    assert [i.title for i in page] == ["B", "C"]
    assert await repo.count(team_id=team_id) == 3
    assert await repo.count() == 3


async def test_list_states_returns_sorted_distinct_states(session: AsyncSession) -> None:
    repo = SqlAlchemyWorkItemRepository(session)
    team_id = await _team_id(session)
    for state in ("in_progress", "backlog", "in_progress", "done"):
        await repo.add(WorkItem(team_id=team_id, title=f"Item {state}", state=state))

    assert await repo.list_states() == ["backlog", "done", "in_progress"]


async def test_list_states_scopes_to_team_and_project(session: AsyncSession) -> None:
    repo = SqlAlchemyWorkItemRepository(session)
    team_id = await _team_id(session)
    other_team_id = await _team_id(session)
    project_id = await _project_id(session, team_id)
    await repo.add(WorkItem(team_id=team_id, project_id=project_id, title="Scoped", state="review"))
    await repo.add(WorkItem(team_id=team_id, title="Team only", state="triage"))
    await repo.add(WorkItem(team_id=other_team_id, title="Elsewhere", state="archived"))

    assert await repo.list_states(team_id=team_id) == ["review", "triage"]
    assert await repo.list_states(project_id=project_id) == ["review"]
    assert await repo.list_states(team_id=team_id, project_id=project_id) == ["review"]


async def test_delete_removes_only_the_given_items(session: AsyncSession) -> None:
    repo = SqlAlchemyWorkItemRepository(session)
    team_id = await _team_id(session)
    keep = WorkItem(team_id=team_id, title="Keep")
    drop = WorkItem(team_id=team_id, title="Drop")
    await repo.add(keep)
    await repo.add(drop)

    await repo.delete([drop.id, uuid4()])  # an unknown id is ignored

    assert [item.title for item in await repo.list(team_id=team_id)] == ["Keep"]


async def test_url_roundtrips(session: AsyncSession) -> None:
    repo = SqlAlchemyWorkItemRepository(session)
    item = WorkItem(
        team_id=await _team_id(session),
        title="Add login",
        url="https://linear.app/acme/issue/ENG-1/add-login",
    )

    await repo.add(item)
    fetched = await repo.get(item.id)

    assert fetched is not None
    assert fetched.url == "https://linear.app/acme/issue/ENG-1/add-login"


async def test_url_defaults_to_none(session: AsyncSession) -> None:
    repo = SqlAlchemyWorkItemRepository(session)
    item = WorkItem(team_id=await _team_id(session), title="Add login")

    await repo.add(item)
    fetched = await repo.get(item.id)

    assert fetched is not None
    assert fetched.url is None


async def test_new_facts_round_trip_and_labels_parents_are_listed(session: AsyncSession) -> None:
    repo = SqlAlchemyWorkItemRepository(session)
    team_id = await _team_id(session)
    parent = WorkItem(team_id=team_id, title="Epic", labels=("Feature",))
    child = WorkItem(
        team_id=team_id,
        title="Task",
        state_type=StateType.UNSTARTED,
        labels=("Bug", "Feature"),
        parent_id=parent.id,
    )
    await repo.add(parent)
    await repo.add(child)

    stored = await repo.get(child.id)

    assert stored is not None
    assert (stored.state_type, stored.labels, stored.parent_id) == (
        StateType.UNSTARTED,
        ("Bug", "Feature"),
        parent.id,
    )
    assert await repo.list_labels(team_id=team_id) == ["Bug", "Feature"]
    assert await repo.parent_ids() == {parent.id}


async def test_delete_detaches_children_instead_of_failing(session: AsyncSession) -> None:
    # Review focus 5: FKs are enforced (conftest); the child outlives its parent.
    repo = SqlAlchemyWorkItemRepository(session)
    team_id = await _team_id(session)
    parent = WorkItem(team_id=team_id, title="Epic")
    child = WorkItem(team_id=team_id, title="Task", parent_id=parent.id)
    await repo.add(parent)
    await repo.add(child)

    await repo.delete([parent.id])
    session.expire_all()
    stored = await repo.get(child.id)

    assert await repo.get(parent.id) is None
    assert stored is not None
    assert stored.parent_id is None


async def test_assignee_roundtrips(session: AsyncSession) -> None:
    repo = SqlAlchemyWorkItemRepository(session)
    item = WorkItem(team_id=await _team_id(session), title="Add login", assignee="Ada Lovelace")

    await repo.add(item)
    fetched = await repo.get(item.id)

    assert fetched is not None
    assert fetched.assignee == "Ada Lovelace"


async def test_assignee_defaults_to_none(session: AsyncSession) -> None:
    repo = SqlAlchemyWorkItemRepository(session)
    item = WorkItem(team_id=await _team_id(session), title="Add login")

    await repo.add(item)
    fetched = await repo.get(item.id)

    assert fetched is not None
    assert fetched.assignee is None
