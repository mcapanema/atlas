import dataclasses
import logging
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.application.sync.service import SyncService, UnknownOrganizationError, UnknownTeamError
from app.domain.events.entities import Event, EventType
from app.domain.organizations.entities import Organization
from app.domain.sync.source import SourceEvent, SourceProject, SourceTeam, SourceWorkItem
from app.domain.teams.entities import Team
from app.domain.work_items.entities import StateType, WorkItem, WorkItemType
from tests.fakes import (
    FakeDataSource,
    InMemoryEventRepository,
    InMemoryOrganizationRepository,
    InMemoryProjectRepository,
    InMemoryTeamRepository,
    InMemoryWorkItemRepository,
)


class Harness:
    def __init__(self, source: FakeDataSource) -> None:
        self.organizations = InMemoryOrganizationRepository()
        self.teams = InMemoryTeamRepository()
        self.projects = InMemoryProjectRepository()
        self.work_items = InMemoryWorkItemRepository()
        self.events = InMemoryEventRepository()
        self.service = SyncService(
            source,
            self.organizations,
            self.teams,
            self.projects,
            self.work_items,
            self.events,
        )


CREATED_AT = datetime(2026, 7, 1, 10, 0, tzinfo=UTC)


def full_source() -> FakeDataSource:
    return FakeDataSource(
        teams=[SourceTeam(external_id="lt1", name="Platform")],
        projects=[SourceProject(external_id="lp1", name="Q3 Launch", team_external_id="lt1")],
        work_items=[
            SourceWorkItem(
                external_id="li1",
                title="Fix login",
                type=WorkItemType.TASK,
                state="In Progress",
                team_external_id="lt1",
                project_external_id="lp1",
                created_at=CREATED_AT,
                events=(
                    SourceEvent(
                        external_id="li1:created",
                        type=EventType.CREATED,
                        occurred_at=CREATED_AT,
                    ),
                    SourceEvent(
                        external_id="lh1",
                        type=EventType.STARTED,
                        occurred_at=datetime(2026, 7, 2, 9, 0, tzinfo=UTC),
                        from_state="Backlog",
                        to_state="In Progress",
                    ),
                ),
            )
        ],
    )


async def seed_org(harness: Harness) -> UUID:
    org = Organization(name="Acme")
    await harness.organizations.add(org)
    return org.id


async def test_first_sync_creates_everything() -> None:
    harness = Harness(full_source())
    org_id = await seed_org(harness)

    summary = await harness.service.sync(org_id)

    assert (summary.teams, summary.projects, summary.work_items, summary.events) == (1, 1, 1, 2)
    team = await harness.teams.get_by_external_id("lt1")
    assert team is not None
    assert team.organization_id == org_id
    project = await harness.projects.get_by_external_id("lp1")
    assert project is not None
    assert project.team_id == team.id
    item = await harness.work_items.get_by_external_id("li1")
    assert item is not None
    assert item.team_id == team.id
    assert item.project_id == project.id
    assert item.created_at == CREATED_AT
    events = await harness.events.list_for_work_item(item.id)
    assert [e.type for e in events] == [EventType.CREATED, EventType.STARTED]


async def test_first_sync_stores_url() -> None:
    source = full_source()
    source.work_items = [
        dataclasses.replace(source.work_items[0], url="https://linear.app/acme/issue/ENG-1")
    ]
    harness = Harness(source)

    await harness.service.sync(await seed_org(harness))

    item = await harness.work_items.get_by_external_id("li1")
    assert item is not None
    assert item.url == "https://linear.app/acme/issue/ENG-1"


async def test_resync_backfills_url_on_item_synced_without_one() -> None:
    source = full_source()
    harness = Harness(source)
    org_id = await seed_org(harness)
    await harness.service.sync(org_id)  # stored with url=None, as before this feature
    source.work_items = [
        dataclasses.replace(source.work_items[0], url="https://linear.app/acme/issue/ENG-1")
    ]

    summary = await harness.service.sync(org_id)

    assert summary.work_items == 1
    item = await harness.work_items.get_by_external_id("li1")
    assert item is not None
    assert item.url == "https://linear.app/acme/issue/ENG-1"


async def test_changed_url_is_updated() -> None:
    source = full_source()
    source.work_items = [dataclasses.replace(source.work_items[0], url="https://linear.app/a/E-1")]
    harness = Harness(source)
    org_id = await seed_org(harness)
    await harness.service.sync(org_id)
    source.work_items = [dataclasses.replace(source.work_items[0], url="https://linear.app/b/E-1")]

    summary = await harness.service.sync(org_id)

    assert summary.work_items == 1
    item = await harness.work_items.get_by_external_id("li1")
    assert item is not None
    assert item.url == "https://linear.app/b/E-1"


async def test_second_sync_is_a_no_op() -> None:
    harness = Harness(full_source())
    org_id = await seed_org(harness)
    await harness.service.sync(org_id)

    summary = await harness.service.sync(org_id)

    assert (summary.teams, summary.projects, summary.work_items, summary.events) == (0, 0, 0, 0)
    assert len(await harness.teams.list()) == 1
    item = await harness.work_items.get_by_external_id("li1")
    assert item is not None
    assert len(await harness.events.list_for_work_item(item.id)) == 2


async def test_renamed_team_is_updated() -> None:
    source = full_source()
    harness = Harness(source)
    org_id = await seed_org(harness)
    await harness.service.sync(org_id)
    source.teams = [SourceTeam(external_id="lt1", name="Platform Engineering")]
    source.projects = []
    source.work_items = []

    summary = await harness.service.sync(org_id)

    assert summary.teams == 1
    team = await harness.teams.get_by_external_id("lt1")
    assert team is not None
    assert team.name == "Platform Engineering"
    assert len(await harness.teams.list()) == 1


async def test_state_change_updates_work_item_and_appends_event() -> None:
    source = full_source()
    harness = Harness(source)
    org_id = await seed_org(harness)
    await harness.service.sync(org_id)

    item_source = source.work_items[0]
    source.work_items = [
        SourceWorkItem(
            external_id=item_source.external_id,
            title=item_source.title,
            type=item_source.type,
            state="Done",
            team_external_id=item_source.team_external_id,
            project_external_id=item_source.project_external_id,
            created_at=item_source.created_at,
            events=(
                *item_source.events,
                SourceEvent(
                    external_id="lh2",
                    type=EventType.COMPLETED,
                    occurred_at=datetime(2026, 7, 3, 9, 0, tzinfo=UTC),
                    from_state="In Progress",
                    to_state="Done",
                ),
            ),
        )
    ]

    summary = await harness.service.sync(org_id)

    assert summary.work_items == 1
    assert summary.events == 1
    item = await harness.work_items.get_by_external_id("li1")
    assert item is not None
    assert item.state == "Done"
    assert len(await harness.events.list_for_work_item(item.id)) == 3


async def test_project_reassigned_to_different_team_is_updated() -> None:
    source = full_source()
    harness = Harness(source)
    org_id = await seed_org(harness)
    source.teams = [*source.teams, SourceTeam(external_id="lt2", name="Growth")]
    await harness.service.sync(org_id)

    source.projects = [SourceProject(external_id="lp1", name="Q3 Launch", team_external_id="lt2")]
    source.work_items = []

    summary = await harness.service.sync(org_id)

    assert summary.projects == 1
    new_team = await harness.teams.get_by_external_id("lt2")
    project = await harness.projects.get_by_external_id("lp1")
    assert new_team is not None
    assert project is not None
    assert project.team_id == new_team.id


async def test_work_item_reassigned_to_different_team_is_updated() -> None:
    source = full_source()
    harness = Harness(source)
    org_id = await seed_org(harness)
    source.teams = [*source.teams, SourceTeam(external_id="lt2", name="Growth")]
    await harness.service.sync(org_id)

    item_source = source.work_items[0]
    source.work_items = [
        SourceWorkItem(
            external_id=item_source.external_id,
            title=item_source.title,
            type=item_source.type,
            state=item_source.state,
            team_external_id="lt2",
            project_external_id=item_source.project_external_id,
            created_at=item_source.created_at,
            events=item_source.events,
        )
    ]

    summary = await harness.service.sync(org_id)

    assert summary.work_items == 1
    new_team = await harness.teams.get_by_external_id("lt2")
    item = await harness.work_items.get_by_external_id("li1")
    assert new_team is not None
    assert item is not None
    assert item.team_id == new_team.id


async def test_work_item_type_change_is_updated() -> None:
    source = full_source()
    harness = Harness(source)
    org_id = await seed_org(harness)
    await harness.service.sync(org_id)

    item_source = source.work_items[0]
    source.work_items = [
        SourceWorkItem(
            external_id=item_source.external_id,
            title=item_source.title,
            type=WorkItemType.BUG,
            state=item_source.state,
            team_external_id=item_source.team_external_id,
            project_external_id=item_source.project_external_id,
            created_at=item_source.created_at,
            events=item_source.events,
        )
    ]

    summary = await harness.service.sync(org_id)

    assert summary.work_items == 1
    item = await harness.work_items.get_by_external_id("li1")
    assert item is not None
    assert item.type == WorkItemType.BUG


async def test_project_with_unknown_team_is_skipped() -> None:
    harness = Harness(
        FakeDataSource(
            projects=[SourceProject(external_id="lp9", name="Orphan", team_external_id="missing")]
        )
    )
    org_id = await seed_org(harness)

    summary = await harness.service.sync(org_id)

    assert summary.projects == 0
    assert await harness.projects.get_by_external_id("lp9") is None


async def test_work_item_with_unknown_team_is_skipped() -> None:
    harness = Harness(
        FakeDataSource(
            work_items=[
                SourceWorkItem(
                    external_id="li9",
                    title="Orphan",
                    type=WorkItemType.TASK,
                    state="Backlog",
                    team_external_id="missing",
                    project_external_id=None,
                    created_at=CREATED_AT,
                    events=(
                        SourceEvent(
                            external_id="li9:created",
                            type=EventType.CREATED,
                            occurred_at=CREATED_AT,
                        ),
                    ),
                )
            ]
        )
    )
    org_id = await seed_org(harness)

    summary = await harness.service.sync(org_id)

    assert summary.work_items == 0
    assert summary.events == 0  # skipping the item must skip its events too
    assert await harness.work_items.get_by_external_id("li9") is None


async def test_work_item_with_unknown_project_is_created_without_project() -> None:
    source = full_source()
    source.projects = []  # "lp1" on the item now resolves to nothing

    harness = Harness(source)
    org_id = await seed_org(harness)

    summary = await harness.service.sync(org_id)

    assert summary.work_items == 1
    item = await harness.work_items.get_by_external_id("li1")
    assert item is not None
    assert item.project_id is None


async def test_project_with_null_team_external_id_is_skipped() -> None:
    harness = Harness(
        FakeDataSource(
            teams=[SourceTeam(external_id="lt1", name="Platform")],
            projects=[SourceProject(external_id="lp9", name="Teamless", team_external_id=None)],
        )
    )
    org_id = await seed_org(harness)

    summary = await harness.service.sync(org_id)

    assert summary.projects == 0
    assert await harness.projects.get_by_external_id("lp9") is None


async def test_unknown_organization_raises_unknown_organization_error() -> None:
    harness = Harness(full_source())

    with pytest.raises(UnknownOrganizationError, match="does not exist"):
        await harness.service.sync(uuid4())


async def test_sync_logs_start_and_summary(caplog: pytest.LogCaptureFixture) -> None:
    harness = Harness(full_source())
    org_id = await seed_org(harness)

    with caplog.at_level(logging.INFO, logger="app.application.sync.service"):
        await harness.service.sync(org_id)

    messages = [record.getMessage() for record in caplog.records]
    assert any("Sync started" in m and str(org_id) in m for m in messages)
    assert any("Sync finished" in m and "teams=1" in m for m in messages)


COMPLETED_AT = datetime(2026, 7, 5, 12, 0, tzinfo=UTC)


def done_without_completion_source() -> FakeDataSource:
    """State says done, but the (truncated) history never recorded a completion."""
    return FakeDataSource(
        teams=[SourceTeam(external_id="lt1", name="Platform")],
        work_items=[
            SourceWorkItem(
                external_id="li2",
                title="Ship report",
                type=WorkItemType.TASK,
                state="Done",
                team_external_id="lt1",
                project_external_id=None,
                created_at=CREATED_AT,
                completed_at=COMPLETED_AT,
                events=(
                    SourceEvent(
                        external_id="li2:created",
                        type=EventType.CREATED,
                        occurred_at=CREATED_AT,
                    ),
                ),
            )
        ],
    )


async def test_done_item_without_completion_event_gets_one_synthesized() -> None:
    harness = Harness(done_without_completion_source())
    org_id = await seed_org(harness)

    summary = await harness.service.sync(org_id)

    assert summary.divergences == 1
    assert summary.events == 2  # created + synthesized completion
    item = await harness.work_items.get_by_external_id("li2")
    assert item is not None
    completions = [
        e for e in await harness.events.list_for_work_item(item.id) if e.type is EventType.COMPLETED
    ]
    assert len(completions) == 1
    assert completions[0].occurred_at == COMPLETED_AT
    assert completions[0].external_id == "li2:completed"
    assert completions[0].to_state == "Done"


async def test_synthesized_completion_is_idempotent_across_syncs() -> None:
    harness = Harness(done_without_completion_source())
    org_id = await seed_org(harness)
    await harness.service.sync(org_id)

    summary = await harness.service.sync(org_id)

    assert summary.events == 0  # nothing new written
    assert summary.divergences == 1  # the divergence still exists at the source
    item = await harness.work_items.get_by_external_id("li2")
    assert item is not None
    events = await harness.events.list_for_work_item(item.id)
    assert sum(1 for e in events if e.type is EventType.COMPLETED) == 1


async def test_done_item_with_real_completion_event_is_not_a_divergence() -> None:
    source = done_without_completion_source()
    item_source = source.work_items[0]
    source.work_items = [
        SourceWorkItem(
            external_id=item_source.external_id,
            title=item_source.title,
            type=item_source.type,
            state=item_source.state,
            team_external_id=item_source.team_external_id,
            project_external_id=None,
            created_at=item_source.created_at,
            completed_at=item_source.completed_at,
            events=(
                *item_source.events,
                SourceEvent(
                    external_id="lh9",
                    type=EventType.COMPLETED,
                    occurred_at=COMPLETED_AT,
                    from_state="In Progress",
                    to_state="Done",
                ),
            ),
        )
    ]
    harness = Harness(source)
    org_id = await seed_org(harness)

    summary = await harness.service.sync(org_id)

    assert summary.divergences == 0
    assert await harness.events.get_by_external_id("li2:completed") is None


async def test_open_item_is_not_a_divergence() -> None:
    harness = Harness(full_source())  # completed_at is None throughout

    summary = await harness.service.sync(await seed_org(harness))

    assert summary.divergences == 0


async def test_sync_batches_event_lookups() -> None:
    # Two work items (each with events) so a regression to "once per work
    # item" would push batch_lookup_calls to 2, not just 1.
    source = FakeDataSource(
        teams=[SourceTeam(external_id="lt1", name="Platform")],
        work_items=[
            SourceWorkItem(
                external_id="li1",
                title="Fix login",
                type=WorkItemType.TASK,
                state="In Progress",
                team_external_id="lt1",
                project_external_id=None,
                created_at=CREATED_AT,
                events=(
                    SourceEvent(
                        external_id="li1:created",
                        type=EventType.CREATED,
                        occurred_at=CREATED_AT,
                    ),
                ),
            ),
            SourceWorkItem(
                external_id="li2",
                title="Ship report",
                type=WorkItemType.TASK,
                state="In Progress",
                team_external_id="lt1",
                project_external_id=None,
                created_at=CREATED_AT,
                events=(
                    SourceEvent(
                        external_id="li2:created",
                        type=EventType.CREATED,
                        occurred_at=CREATED_AT,
                    ),
                ),
            ),
        ],
    )
    harness = Harness(source)
    org_id = await seed_org(harness)

    await harness.service.sync(org_id)

    # One batched existence query for the whole run, zero per-event SELECTs.
    assert harness.events.single_lookup_calls == 0
    assert harness.events.batch_lookup_calls == 1


async def test_sync_without_org_creates_one_from_source() -> None:
    harness = Harness(full_source())

    summary = await harness.service.sync()

    orgs = await harness.organizations.list()
    assert [o.name for o in orgs] == ["Acme Workspace"]
    assert summary.teams == 1
    team = await harness.teams.get_by_external_id("lt1")
    assert team is not None
    assert team.organization_id == orgs[0].id


async def test_sync_without_org_reuses_the_single_existing_org() -> None:
    harness = Harness(full_source())
    org_id = await seed_org(harness)

    await harness.service.sync()

    assert [o.id for o in await harness.organizations.list()] == [org_id]
    team = await harness.teams.get_by_external_id("lt1")
    assert team is not None
    assert team.organization_id == org_id


async def test_sync_without_org_is_ambiguous_with_multiple_orgs() -> None:
    harness = Harness(full_source())
    await harness.organizations.add(Organization(name="A"))
    await harness.organizations.add(Organization(name="B"))

    with pytest.raises(ValueError, match="specify organization_id"):
        await harness.service.sync()


def _todo(external_id: str, team_external_id: str = "lt1") -> SourceWorkItem:
    return SourceWorkItem(
        external_id=external_id,
        title=f"Item {external_id}",
        type=WorkItemType.TASK,
        state="Todo",
        team_external_id=team_external_id,
        project_external_id=None,
        created_at=CREATED_AT,
        events=(
            SourceEvent(
                external_id=f"{external_id}:created",
                type=EventType.CREATED,
                occurred_at=CREATED_AT,
            ),
        ),
    )


async def test_item_gone_from_source_is_deleted_with_its_events() -> None:
    source = full_source()
    source.work_items = [*source.work_items, _todo("li2")]
    harness = Harness(source)
    org_id = await seed_org(harness)
    await harness.service.sync(org_id)
    gone = await harness.work_items.get_by_external_id("li2")
    assert gone is not None
    source.work_items = source.work_items[:1]  # li2 deleted or trashed upstream

    summary = await harness.service.sync(org_id)

    assert summary.deleted == 1
    assert await harness.work_items.get_by_external_id("li2") is None
    assert await harness.events.list_for_work_item(gone.id) == []
    assert await harness.work_items.get_by_external_id("li1") is not None
    assert (await harness.service.sync(org_id)).deleted == 0  # idempotent


async def test_empty_fetch_deletes_nothing() -> None:
    source = full_source()
    harness = Harness(source)
    org_id = await seed_org(harness)
    await harness.service.sync(org_id)
    source.work_items = []

    summary = await harness.service.sync(org_id)

    assert summary.deleted == 0
    assert await harness.work_items.get_by_external_id("li1") is not None


async def test_team_with_no_live_items_keeps_its_items() -> None:
    # Credentials that lost a team's access see none of its issues; that's
    # lost visibility, not deletion.
    source = full_source()
    source.teams = [*source.teams, SourceTeam(external_id="lt2", name="Private")]
    source.work_items = [*source.work_items, _todo("li2", team_external_id="lt2")]
    harness = Harness(source)
    org_id = await seed_org(harness)
    await harness.service.sync(org_id)
    source.work_items = source.work_items[:1]

    summary = await harness.service.sync(org_id)

    assert summary.deleted == 0
    assert await harness.work_items.get_by_external_id("li2") is not None


async def test_items_without_external_id_are_never_pruned() -> None:
    harness = Harness(full_source())
    org_id = await seed_org(harness)
    await harness.service.sync(org_id)
    team = await harness.teams.get_by_external_id("lt1")
    assert team is not None
    manual = WorkItem(team_id=team.id, title="Logged via the events API")
    await harness.work_items.add(manual)

    summary = await harness.service.sync(org_id)

    assert summary.deleted == 0
    assert await harness.work_items.get(manual.id) is not None


async def test_item_moved_to_another_team_upstream_is_not_pruned() -> None:
    source = full_source()
    source.teams = [*source.teams, SourceTeam(external_id="lt2", name="Mobile")]
    source.work_items = [*source.work_items, _todo("li2")]
    harness = Harness(source)
    org_id = await seed_org(harness)
    await harness.service.sync(org_id)
    source.work_items = [source.work_items[0], _todo("li2", team_external_id="lt2")]

    summary = await harness.service.sync(org_id)

    assert summary.deleted == 0
    moved = await harness.work_items.get_by_external_id("li2")
    lt2 = await harness.teams.get_by_external_id("lt2")
    assert moved is not None
    assert lt2 is not None
    assert moved.team_id == lt2.id


def _facts_source(*items: SourceWorkItem) -> FakeDataSource:
    return FakeDataSource(
        teams=[SourceTeam(external_id="lt1", name="Platform")], work_items=list(items)
    )


def _source_item(external_id: str, **fields: object) -> SourceWorkItem:
    return dataclasses.replace(
        SourceWorkItem(
            external_id=external_id,
            title=f"Item {external_id}",
            type=WorkItemType.TASK,
            state="Todo",
            team_external_id="lt1",
            project_external_id=None,
            created_at=CREATED_AT,
        ),
        **fields,  # type: ignore[arg-type]
    )


async def test_sync_stores_state_type_labels_and_event_facts() -> None:
    event = SourceEvent(
        external_id="h1:blocker:ab:DEP-1",
        type=EventType.BLOCKER_ADDED,
        occurred_at=CREATED_AT,
        detail="DEP-1",
    )
    harness = Harness(
        _facts_source(
            _source_item("li1", state_type=StateType.UNSTARTED, labels=("Bug",), events=(event,))
        )
    )

    await harness.service.sync()
    [item] = await harness.work_items.list()
    [stored] = await harness.events.list_for_work_item(item.id)

    assert (item.state_type, item.labels) == (StateType.UNSTARTED, ("Bug",))
    assert (stored.type, stored.detail) == (EventType.BLOCKER_ADDED, "DEP-1")


async def test_label_change_updates_the_item() -> None:
    source = _facts_source(_source_item("li1", labels=("Bug",)))
    harness = Harness(source)
    await harness.service.sync()
    source.work_items = [_source_item("li1", labels=("Bug", "Urgent"))]

    summary = await harness.service.sync()
    [item] = await harness.work_items.list()

    assert item.labels == ("Bug", "Urgent")
    assert summary.work_items == 1


async def test_parent_synced_after_its_child_is_linked() -> None:
    harness = Harness(
        _facts_source(_source_item("child", parent_external_id="parent"), _source_item("parent"))
    )

    await harness.service.sync()
    by_eid = {item.external_id: item for item in await harness.work_items.list()}

    assert by_eid["child"].parent_id == by_eid["parent"].id
    assert by_eid["parent"].parent_id is None


async def test_parent_outside_atlas_leaves_no_link() -> None:
    harness = Harness(_facts_source(_source_item("child", parent_external_id="elsewhere")))

    await harness.service.sync()
    [item] = await harness.work_items.list()

    assert item.parent_id is None


async def test_sync_fills_missing_state_types_once_and_never_overwrites() -> None:
    harness = Harness(
        _facts_source(
            _source_item(
                "li1",
                events=(
                    SourceEvent(
                        external_id="h1",
                        type=EventType.STARTED,
                        occurred_at=CREATED_AT,
                        from_state_type=StateType.BACKLOG,
                        to_state_type=StateType.STARTED,
                    ),
                    SourceEvent(
                        external_id="h2",
                        type=EventType.STATE_CHANGED,
                        occurred_at=CREATED_AT,
                        from_state_type=StateType.STARTED,
                        to_state_type=StateType.STARTED,
                    ),
                ),
            )
        )
    )
    await harness.service.sync()
    [item] = await harness.work_items.list()
    # Simulate rows stored before ADR-0011: h1 untyped, h2 typed differently.
    stored_before = await harness.events.list_for_work_item(item.id)
    await harness.events.delete_for_work_items([item.id])
    for event in stored_before:
        stale = None if event.external_id == "h1" else StateType.UNSTARTED
        await harness.events.add(
            dataclasses.replace(event, from_state_type=stale, to_state_type=stale)
        )

    first = await harness.service.sync()
    second = await harness.service.sync()
    stored = {e.external_id: e for e in await harness.events.list_for_work_item(item.id)}

    assert (first.state_types_filled, second.state_types_filled) == (1, 0)
    assert stored["h1"].to_state_type is StateType.STARTED
    assert stored["h2"].to_state_type is StateType.UNSTARTED  # never overwritten
    assert second.events == 0


async def test_sync_fills_an_empty_from_type_beside_a_known_to_type() -> None:
    # A reopen out of Duplicate stored before "duplicate" mapped to canceled.
    reopen = SourceEvent(
        external_id="h1",
        type=EventType.STATE_CHANGED,
        occurred_at=CREATED_AT,
        from_state="Duplicate",
        to_state="Todo",
        from_state_type=StateType.CANCELED,
        to_state_type=StateType.UNSTARTED,
    )
    harness = Harness(_facts_source(_source_item("li1", events=(reopen,))))
    await harness.service.sync()
    [item] = await harness.work_items.list()
    [stored] = [
        e for e in await harness.events.list_for_work_item(item.id) if e.external_id == "h1"
    ]
    await harness.events.delete_for_work_items([item.id])
    await harness.events.add(dataclasses.replace(stored, from_state_type=None))

    first = await harness.service.sync()
    second = await harness.service.sync()
    [refilled] = [
        e for e in await harness.events.list_for_work_item(item.id) if e.external_id == "h1"
    ]

    assert (first.state_types_filled, second.state_types_filled) == (1, 0)
    assert (refilled.from_state_type, refilled.to_state_type) == (
        StateType.CANCELED,
        StateType.UNSTARTED,
    )


async def test_pruning_a_parent_keeps_its_children_unlinked() -> None:
    source = _facts_source(
        _source_item("child", parent_external_id="parent"), _source_item("parent")
    )
    harness = Harness(source)
    await harness.service.sync()
    source.work_items = [_source_item("child")]

    summary = await harness.service.sync()
    [item] = await harness.work_items.list()

    assert summary.deleted == 1
    assert (item.external_id, item.parent_id) == ("child", None)


def _start_typed_as(source: FakeDataSource, event_type: EventType) -> None:
    """Re-type li1's start event, as an older (or newer) connector mapping would."""
    item = source.work_items[0]
    created, started = item.events
    source.work_items = [
        dataclasses.replace(item, events=(created, dataclasses.replace(started, type=event_type)))
    ]


async def test_rebuild_replaces_events_stored_by_an_older_mapping() -> None:
    source = full_source()
    _start_typed_as(source, EventType.STATE_CHANGED)  # the old mapping's reading
    harness = Harness(source)
    org_id = await seed_org(harness)
    await harness.service.sync(org_id)
    item = await harness.work_items.get_by_external_id("li1")
    assert item is not None
    recorded = Event(work_item_id=item.id, type=EventType.BLOCKED, occurred_at=CREATED_AT)
    await harness.events.add(recorded)  # recorded through the events API: no external_id
    _start_typed_as(source, EventType.STARTED)  # the fixed mapping

    plain = await harness.service.sync(org_id)
    stale = {e.external_id: e.type for e in await harness.events.list_for_work_item(item.id)}
    rebuilt = await harness.service.sync(org_id, rebuild=True)

    events = await harness.events.list_for_work_item(item.id)
    assert stale["lh1"] is EventType.STATE_CHANGED  # insert-only: a plain sync never heals it
    assert {e.external_id: e.type for e in events if e.external_id is not None} == {
        "li1:created": EventType.CREATED,
        "lh1": EventType.STARTED,
    }
    assert recorded.id in {e.id for e in events}
    assert (plain.rebuilt, rebuilt.rebuilt, rebuilt.events) == (0, 1, 2)
    assert rebuilt.organization_id == org_id


async def test_rebuild_leaves_items_the_run_did_not_return_alone() -> None:
    source = full_source()
    harness = Harness(source)
    org_id = await seed_org(harness)
    await harness.service.sync(org_id)
    item = await harness.work_items.get_by_external_id("li1")
    assert item is not None
    source.work_items = []  # the team returned nothing: lost access, not deletion

    summary = await harness.service.sync(org_id, rebuild=True)

    assert (summary.rebuilt, summary.deleted) == (0, 0)
    assert len(await harness.events.list_for_work_item(item.id)) == 2


def _done_without_history(source: FakeDataSource, *, real_completion: bool) -> None:
    """li1 is done upstream; its history has a COMPLETED event only when `real_completion`."""
    item = source.work_items[0]
    done_at = datetime(2026, 7, 5, 9, 0, tzinfo=UTC)
    events = item.events
    if real_completion:
        events = (
            *events,
            SourceEvent(
                external_id="lh2",
                type=EventType.COMPLETED,
                occurred_at=done_at,
                from_state="In Progress",
                to_state="Done",
            ),
        )
    source.work_items = [
        dataclasses.replace(item, completed_at=done_at, state="Done", events=events)
    ]


async def test_rebuild_drops_a_synthesized_completion_once_history_has_the_real_one() -> None:
    source = full_source()
    _done_without_history(source, real_completion=False)
    harness = Harness(source)
    org_id = await seed_org(harness)
    await harness.service.sync(org_id)  # synthesizes li1:completed (a divergence)
    item = await harness.work_items.get_by_external_id("li1")
    assert item is not None
    _done_without_history(source, real_completion=True)  # the fixed mapping emits the real one

    await harness.service.sync(org_id, rebuild=True)

    eids = {e.external_id for e in await harness.events.list_for_work_item(item.id)}
    assert "lh2" in eids
    assert "li1:completed" not in eids


async def test_rebuild_re_synthesizes_a_completion_history_still_lacks() -> None:
    source = full_source()
    _done_without_history(source, real_completion=False)
    harness = Harness(source)
    org_id = await seed_org(harness)
    await harness.service.sync(org_id)
    item = await harness.work_items.get_by_external_id("li1")
    assert item is not None

    summary = await harness.service.sync(org_id, rebuild=True)

    eids = {e.external_id for e in await harness.events.list_for_work_item(item.id)}
    assert "li1:completed" in eids
    assert summary.divergences == 1


def _typed_items(team_external_id: str = "lt1") -> list[SourceWorkItem]:
    """full_source()'s item with a typed lh1 event, team replaceable."""
    item = full_source().work_items[0]
    created, started = item.events
    typed = dataclasses.replace(
        started, from_state_type=StateType.UNSTARTED, to_state_type=StateType.STARTED
    )
    return [dataclasses.replace(item, events=(created, typed), team_external_id=team_external_id)]


async def test_rebuild_still_fills_state_types_on_stored_events() -> None:
    source = full_source()
    harness = Harness(source)
    org_id = await seed_org(harness)
    await harness.service.sync(org_id)  # lh1 stored untyped
    # The item's team is no longer resolvable, so the rebuild skips it.
    source.work_items = _typed_items(team_external_id="lt-gone")

    summary = await harness.service.sync(org_id, rebuild=True)

    assert summary.rebuilt == 0
    assert summary.state_types_filled == 1
    stored = await harness.events.get_by_external_id("lh1")
    assert stored is not None
    assert stored.to_state_type is StateType.STARTED


async def test_rebuild_of_a_resolvable_item_does_not_count_its_events_as_filled() -> None:
    source = full_source()
    harness = Harness(source)
    org_id = await seed_org(harness)
    await harness.service.sync(org_id)  # lh1 stored untyped
    source.work_items = _typed_items()

    summary = await harness.service.sync(org_id, rebuild=True)

    assert summary.rebuilt == 1
    assert summary.state_types_filled == 0


async def _synced_two_teams(harness: Harness, source: FakeDataSource) -> UUID:
    """Org sync of lt1 (li1) + lt2 (li2); returns lt1's Atlas id."""
    source.teams = [*source.teams, SourceTeam(external_id="lt2", name="Mobile")]
    source.work_items = [*source.work_items, _todo("li2", team_external_id="lt2")]
    await harness.service.sync(await seed_org(harness))
    team = await harness.teams.get_by_external_id("lt1")
    assert team is not None
    return team.id


async def test_sync_team_writes_only_that_teams_items() -> None:
    source = full_source()
    harness = Harness(source)
    lt1_id = await _synced_two_teams(harness, source)
    source.work_items = [
        dataclasses.replace(source.work_items[0], title="Fix login (renamed)"),
        dataclasses.replace(source.work_items[1], title="Other team's change"),
    ]

    summary = await harness.service.sync_team(lt1_id)

    assert summary.work_items == 1
    mine = await harness.work_items.get_by_external_id("li1")
    theirs = await harness.work_items.get_by_external_id("li2")
    assert mine is not None
    assert theirs is not None
    assert mine.title == "Fix login (renamed)"
    assert theirs.title == "Item li2"  # untouched: not this team's sync


async def test_sync_team_reports_the_teams_organization() -> None:
    source = full_source()
    harness = Harness(source)
    lt1_id = await _synced_two_teams(harness, source)
    team = await harness.teams.get(lt1_id)
    assert team is not None

    summary = await harness.service.sync_team(lt1_id)

    assert summary.organization_id == team.organization_id


async def test_sync_team_does_not_prune_items_it_did_not_return() -> None:
    # Moved to lt2 upstream: lt1's filtered fetch no longer returns li1, but
    # that is not deletion. Only an org-wide sync may prune.
    source = full_source()
    harness = Harness(source)
    lt1_id = await _synced_two_teams(harness, source)
    source.work_items = [
        dataclasses.replace(source.work_items[0], team_external_id="lt2"),
        source.work_items[1],
        # A live lt1 item, so lt1 counts as "returned live work": without it
        # the empty-fetch guard alone would spare li1 and this test proves nothing.
        _todo("li3"),
    ]

    summary = await harness.service.sync_team(lt1_id)

    assert summary.deleted == 0
    assert await harness.work_items.get_by_external_id("li1") is not None


async def test_sync_team_adopts_an_item_moved_into_it_upstream() -> None:
    source = full_source()
    harness = Harness(source)
    lt1_id = await _synced_two_teams(harness, source)
    source.work_items = [source.work_items[0], _todo("li2", team_external_id="lt1")]

    await harness.service.sync_team(lt1_id)

    moved = await harness.work_items.get_by_external_id("li2")
    assert moved is not None
    assert moved.team_id == lt1_id


async def test_sync_team_creates_the_teams_new_projects() -> None:
    source = full_source()
    harness = Harness(source)
    lt1_id = await _synced_two_teams(harness, source)
    source.projects = [
        *source.projects,
        SourceProject(external_id="lp2", name="Q4 Launch", team_external_id="lt1"),
    ]

    summary = await harness.service.sync_team(lt1_id)

    assert summary.projects == 1
    project = await harness.projects.get_by_external_id("lp2")
    assert project is not None
    assert project.team_id == lt1_id


async def test_sync_team_unknown_team_raises_unknown_team_error() -> None:
    harness = Harness(full_source())

    with pytest.raises(UnknownTeamError, match="does not exist"):
        await harness.service.sync_team(uuid4())


async def test_sync_team_without_external_id_is_a_value_error() -> None:
    harness = Harness(full_source())
    org_id = await seed_org(harness)
    manual = Team(organization_id=org_id, name="Made in Atlas")
    await harness.teams.add(manual)

    with pytest.raises(ValueError, match="not synced from a source"):
        await harness.service.sync_team(manual.id)


async def test_org_sync_stamps_every_synced_team() -> None:
    harness = Harness(full_source())
    org_id = await seed_org(harness)
    before = datetime.now(UTC)

    await harness.service.sync(org_id)

    team = await harness.teams.get_by_external_id("lt1")
    assert team is not None
    assert team.last_synced_at is not None
    assert team.last_synced_at >= before


async def test_team_sync_stamps_only_that_team() -> None:
    source = full_source()
    harness = Harness(source)
    lt1_id = await _synced_two_teams(harness, source)
    other = await harness.teams.get_by_external_id("lt2")
    assert other is not None
    other_stamp = other.last_synced_at

    await harness.service.sync_team(lt1_id)

    mine = await harness.teams.get(lt1_id)
    theirs = await harness.teams.get_by_external_id("lt2")
    assert mine is not None
    assert theirs is not None
    assert other_stamp is not None
    assert mine.last_synced_at is not None
    assert mine.last_synced_at >= other_stamp
    assert theirs.last_synced_at == other_stamp
