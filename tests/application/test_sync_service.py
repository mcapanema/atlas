import logging
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.application.sync.service import SyncService, UnknownOrganizationError
from app.domain.events.entities import Event, EventType
from app.domain.organizations.entities import Organization
from app.domain.projects.entities import Project
from app.domain.sync.source import SourceEvent, SourceProject, SourceTeam, SourceWorkItem
from app.domain.teams.entities import Team
from app.domain.work_items.entities import WorkItem, WorkItemType


class InMemoryOrganizationRepository:
    def __init__(self) -> None:
        self._orgs: dict[UUID, Organization] = {}

    async def add(self, organization: Organization) -> None:
        self._orgs[organization.id] = organization

    async def list(self) -> list[Organization]:
        return list(self._orgs.values())

    async def get(self, organization_id: UUID) -> Organization | None:
        return self._orgs.get(organization_id)


class InMemoryTeamRepository:
    def __init__(self) -> None:
        self._teams: dict[UUID, Team] = {}

    async def add(self, team: Team) -> None:
        self._teams[team.id] = team

    async def update(self, team: Team) -> None:
        self._teams[team.id] = team

    async def list(self) -> list[Team]:
        return list(self._teams.values())

    async def get(self, team_id: UUID) -> Team | None:
        return self._teams.get(team_id)

    async def get_by_external_id(self, external_id: str) -> Team | None:
        return next((t for t in self._teams.values() if t.external_id == external_id), None)


class InMemoryProjectRepository:
    def __init__(self) -> None:
        self._projects: dict[UUID, Project] = {}

    async def add(self, project: Project) -> None:
        self._projects[project.id] = project

    async def update(self, project: Project) -> None:
        self._projects[project.id] = project

    async def list(self) -> list[Project]:
        return list(self._projects.values())

    async def get(self, project_id: UUID) -> Project | None:
        return self._projects.get(project_id)

    async def get_by_external_id(self, external_id: str) -> Project | None:
        return next(
            (p for p in self._projects.values() if p.external_id == external_id), None
        )


class InMemoryWorkItemRepository:
    def __init__(self) -> None:
        self._items: dict[UUID, WorkItem] = {}

    async def add(self, work_item: WorkItem) -> None:
        self._items[work_item.id] = work_item

    async def update(self, work_item: WorkItem) -> None:
        self._items[work_item.id] = work_item

    async def list(
        self, *, team_id: UUID | None = None, project_id: UUID | None = None
    ) -> list[WorkItem]:
        items = list(self._items.values())
        if team_id is not None:
            items = [i for i in items if i.team_id == team_id]
        if project_id is not None:
            items = [i for i in items if i.project_id == project_id]
        return items

    async def get(self, work_item_id: UUID) -> WorkItem | None:
        return self._items.get(work_item_id)

    async def get_by_external_id(self, external_id: str) -> WorkItem | None:
        return next(
            (i for i in self._items.values() if i.external_id == external_id), None
        )


class InMemoryEventRepository:
    def __init__(self) -> None:
        self._events: dict[UUID, Event] = {}
        self.single_lookup_calls = 0
        self.batch_lookup_calls = 0

    async def add(self, event: Event) -> None:
        self._events[event.id] = event

    async def list_for_work_item(self, work_item_id: UUID) -> list[Event]:
        return sorted(
            (e for e in self._events.values() if e.work_item_id == work_item_id),
            key=lambda e: e.occurred_at,
        )

    async def list_for_work_items(self, work_item_ids: list[UUID]) -> list[Event]:
        wanted = set(work_item_ids)
        return sorted(
            (e for e in self._events.values() if e.work_item_id in wanted),
            key=lambda e: e.occurred_at,
        )

    async def get_by_external_id(self, external_id: str) -> Event | None:
        self.single_lookup_calls += 1
        return next(
            (e for e in self._events.values() if e.external_id == external_id), None
        )

    async def existing_external_ids(self, external_ids: list[str]) -> set[str]:
        self.batch_lookup_calls += 1
        wanted = set(external_ids)
        return {
            e.external_id
            for e in self._events.values()
            if e.external_id is not None and e.external_id in wanted
        }


class FakeDataSource:
    def __init__(
        self,
        teams: list[SourceTeam] | None = None,
        projects: list[SourceProject] | None = None,
        work_items: list[SourceWorkItem] | None = None,
    ) -> None:
        self.teams = teams or []
        self.projects = projects or []
        self.work_items = work_items or []

    async def fetch_teams(self) -> list[SourceTeam]:
        return self.teams

    async def fetch_projects(self) -> list[SourceProject]:
        return self.projects

    async def fetch_work_items(self) -> list[SourceWorkItem]:
        return self.work_items


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
    assert team is not None and team.organization_id == org_id
    project = await harness.projects.get_by_external_id("lp1")
    assert project is not None and project.team_id == team.id
    item = await harness.work_items.get_by_external_id("li1")
    assert item is not None
    assert item.team_id == team.id
    assert item.project_id == project.id
    assert item.created_at == CREATED_AT
    events = await harness.events.list_for_work_item(item.id)
    assert [e.type for e in events] == [EventType.CREATED, EventType.STARTED]


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
    assert team is not None and team.name == "Platform Engineering"
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
            events=item_source.events
            + (
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
    assert item is not None and item.state == "Done"
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
    assert new_team is not None and project is not None
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
    assert new_team is not None and item is not None
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
    assert item is not None and item.type == WorkItemType.BUG


async def test_project_with_unknown_team_is_skipped() -> None:
    harness = Harness(
        FakeDataSource(
            projects=[
                SourceProject(external_id="lp9", name="Orphan", team_external_id="missing")
            ]
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
        e
        for e in await harness.events.list_for_work_item(item.id)
        if e.type is EventType.COMPLETED
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
            events=item_source.events
            + (
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
