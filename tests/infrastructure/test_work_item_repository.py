from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.people.entities import Person
from app.domain.projects.entities import Project
from app.domain.teams.entities import Team
from app.domain.work_items.entities import StateType, WorkItem, WorkItemType
from app.infrastructure.repositories.people import SqlAlchemyPersonRepository
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


async def _person(
    session: AsyncSession, name: str = "Ada Lovelace", display_name: str | None = None
) -> Person:
    person = Person(organization_id=uuid4(), name=name, display_name=display_name)
    await SqlAlchemyPersonRepository(session).add(person)
    return person


async def test_work_item_assignee_resolves_from_person(session: AsyncSession) -> None:
    repo = SqlAlchemyWorkItemRepository(session)
    person = await _person(session)
    item = WorkItem(team_id=await _team_id(session), title="Add login", assignee_id=person.id)

    await repo.add(item)
    session.expire_all()
    fetched = await repo.get(item.id)

    assert fetched is not None
    assert fetched.assignee == "Ada Lovelace"
    assert fetched.assignee_id == person.id


async def test_work_item_assignee_prefers_display_name(session: AsyncSession) -> None:
    repo = SqlAlchemyWorkItemRepository(session)
    person = await _person(session, display_name="Ada L.")
    team_id = await _team_id(session)
    item = WorkItem(team_id=team_id, title="Add login", assignee_id=person.id)

    await repo.add(item)
    session.expire_all()
    fetched = await repo.get(item.id)
    listed = await repo.list(team_id=team_id)

    assert fetched is not None
    assert fetched.assignee == "Ada L."
    assert [i.assignee for i in listed] == ["Ada L."]


async def test_reassigning_a_work_item_refreshes_the_resolved_name(session: AsyncSession) -> None:
    repo = SqlAlchemyWorkItemRepository(session)
    ada = await _person(session)
    grace = await _person(session, "Grace Hopper")
    item = WorkItem(team_id=await _team_id(session), title="Add login", assignee_id=ada.id)
    await repo.add(item)
    await repo.get(item.id)

    await repo.update(replace(item, assignee_id=grace.id))
    fetched = await repo.get(item.id)

    assert fetched is not None
    assert fetched.assignee == "Grace Hopper"


async def test_unassigned_work_item_reads_none(session: AsyncSession) -> None:
    repo = SqlAlchemyWorkItemRepository(session)
    item = WorkItem(team_id=await _team_id(session), title="Add login")

    await repo.add(item)
    session.expire_all()
    fetched = await repo.get(item.id)

    assert fetched is not None
    assert fetched.assignee is None
    assert fetched.assignee_id is None


async def test_team_ids_by_project_groups_distinct_teams(session: AsyncSession) -> None:
    repo = SqlAlchemyWorkItemRepository(session)
    team_a, team_b = await _team_id(session), await _team_id(session)
    project_p = await _project_id(session, team_a)
    project_q = await _project_id(session, team_a)
    await repo.add(WorkItem(team_id=team_a, title="1", project_id=project_p))
    await repo.add(WorkItem(team_id=team_a, title="2", project_id=project_p))
    await repo.add(WorkItem(team_id=team_b, title="3", project_id=project_p))
    await repo.add(WorkItem(team_id=team_a, title="4", project_id=project_q))
    await repo.add(WorkItem(team_id=team_b, title="5"))

    assert await repo.team_ids_by_project() == {
        project_p: frozenset({team_a, team_b}),
        project_q: frozenset({team_a}),
    }


async def test_get_by_keys_returns_items_by_key(session: AsyncSession) -> None:
    repo = SqlAlchemyWorkItemRepository(session)
    team_id = await _team_id(session)
    items = {key: WorkItem(team_id=team_id, title="t", key=key) for key in ("OPS-1", "OPS-2", None)}
    for item in items.values():
        await repo.add(item)

    found = await repo.get_by_keys(["OPS-1", "OPS-9"], team_ids={team_id})
    assert set(found) == {"OPS-1"}
    assert found["OPS-1"].id == items["OPS-1"].id
    assert await repo.get_by_keys([], team_ids={team_id}) == {}


async def test_get_by_keys_filters_by_team(session: AsyncSession) -> None:
    repo = SqlAlchemyWorkItemRepository(session)
    team_a = await _team_id(session)
    team_b = await _team_id(session)
    item_a = WorkItem(team_id=team_a, title="a", key="OPS-1")
    await repo.add(item_a)
    await repo.add(WorkItem(team_id=team_b, title="b", key="OPS-1"))

    found = await repo.get_by_keys(["OPS-1"], team_ids={team_a})

    assert found["OPS-1"].id == item_a.id
    assert await repo.get_by_keys(["OPS-1"], team_ids=set()) == {}


async def test_get_by_keys_returns_one_item_per_key(session: AsyncSession) -> None:
    repo = SqlAlchemyWorkItemRepository(session)
    team_id = await _team_id(session)
    await repo.add(WorkItem(team_id=team_id, title="old", key="OPS-1"))
    await repo.add(WorkItem(team_id=team_id, title="new", key="OPS-1"))

    found = await repo.get_by_keys(["OPS-1"], team_ids={team_id})

    assert list(found) == ["OPS-1"]
