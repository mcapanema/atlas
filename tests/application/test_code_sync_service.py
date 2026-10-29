from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from app.application.codebases.sync import CodeSyncService, CodeSyncSummary
from app.application.sync.service import SyncPhase, UnknownOrganizationError
from app.domain.codebases.entities import DeploymentStatus
from app.domain.events.entities import EventType
from app.domain.organizations.entities import Organization
from app.domain.sync.source import SourceCodebase, SourceDeployment, SourcePullRequest
from app.domain.teams.entities import Team
from app.domain.work_items.entities import WorkItem
from tests.fakes import (
    InMemoryCodebaseRepository,
    InMemoryCodeHostSource,
    InMemoryDeploymentRepository,
    InMemoryEventRepository,
    InMemoryOrganizationRepository,
    InMemoryPullRequestRepository,
    InMemoryTeamRepository,
    InMemoryWorkItemRepository,
)

NOW = datetime(2026, 10, 28, 12, tzinfo=UTC)
T1 = datetime(2026, 10, 20, 9, tzinfo=UTC)
T2 = datetime(2026, 10, 21, 9, tzinfo=UTC)
# Inside the one-day overlap of a second sync.
RECENT = NOW - timedelta(hours=2)


class Harness:
    def __init__(self, source: InMemoryCodeHostSource) -> None:
        self.org = Organization(name="Acme")
        self.team_id = uuid4()
        self.organizations = InMemoryOrganizationRepository()
        self.teams = InMemoryTeamRepository()
        self.codebases = InMemoryCodebaseRepository()
        self.pull_requests = InMemoryPullRequestRepository()
        self.deployments = InMemoryDeploymentRepository()
        self.work_items = InMemoryWorkItemRepository()
        self.events = InMemoryEventRepository()
        self.source = source
        self.service = CodeSyncService(
            source,
            self.organizations,
            self.teams,
            self.codebases,
            self.pull_requests,
            self.deployments,
            self.work_items,
            self.events,
        )

    async def start(self) -> UUID:
        await self.organizations.add(self.org)
        await self.teams.add(Team(organization_id=self.org.id, name="Platform", id=self.team_id))
        return self.org.id

    async def map_all(self) -> None:
        for codebase in await self.codebases.list(self.org.id):
            await self.codebases.update(replace(codebase, team_id=self.team_id))

    async def sync(self) -> CodeSyncSummary:
        return await self.service.sync(self.org.id, now=NOW)

    async def item_events(self, item: WorkItem) -> list[tuple[EventType, datetime, str | None]]:
        return [
            (e.type, e.occurred_at, e.detail) for e in await self.events.list_for_work_item(item.id)
        ]


def pr(**kwargs: object) -> SourcePullRequest:
    base: dict[str, object] = {
        "external_id": "pr12",
        "number": 12,
        "title": "Fix",
        "opened_at": T1,
        "work_item_keys": ("DEP-1",),
    }
    return SourcePullRequest(**{**base, **kwargs})  # type: ignore[arg-type]


def deployment(**kwargs: object) -> SourceDeployment:
    base: dict[str, object] = {
        "external_id": "d1",
        "environment": "production",
        "sha": "abc",
        "started_at": T1,
        "status": DeploymentStatus.PENDING,
    }
    return SourceDeployment(**{**base, **kwargs})  # type: ignore[arg-type]


def api_source(
    pull_requests: dict[str, list[SourcePullRequest]] | None = None,
    deployments: dict[str, list[SourceDeployment]] | None = None,
) -> InMemoryCodeHostSource:
    return InMemoryCodeHostSource(
        codebases=[SourceCodebase(external_id="r1", name="acme/api")],
        pull_requests=pull_requests,
        deployments=deployments,
    )


async def seeded(source: InMemoryCodeHostSource) -> Harness:
    """A harness whose codebases were synced once and then mapped to a team."""
    h = Harness(source)
    await h.start()
    await h.sync()
    await h.map_all()
    source.calls.clear()
    return h


async def test_sync_creates_unmapped_codebases_and_fetches_nothing() -> None:
    source = InMemoryCodeHostSource(
        codebases=[
            SourceCodebase(external_id="r1", name="acme/api"),
            SourceCodebase(external_id="r2", name="acme/web", url="https://h/acme/web"),
        ]
    )
    h = Harness(source)
    await h.start()

    summary = await h.sync()

    assert summary.codebases == 2
    assert source.calls == []
    stored = {c.name: c for c in await h.codebases.list(h.org.id)}
    assert stored["acme/web"].url == "https://h/acme/web"
    assert all(c.team_id is None and c.last_synced_at is None for c in stored.values())


async def test_rename_updates_codebase_and_never_prunes() -> None:
    source = InMemoryCodeHostSource(
        codebases=[
            SourceCodebase(external_id="r1", name="acme/api"),
            SourceCodebase(external_id="r2", name="acme/web"),
        ]
    )
    h = Harness(source)
    await h.start()
    await h.sync()

    source.codebases = [SourceCodebase(external_id="r1", name="acme/api-v2")]
    summary = await h.sync()

    assert summary.codebases == 1
    assert {c.name for c in await h.codebases.list(h.org.id)} == {"acme/api-v2", "acme/web"}


async def test_first_fetch_uses_backfill_window() -> None:
    source = api_source()
    h = await seeded(source)

    await h.sync()

    assert len(source.calls) == 2
    assert {since for _, _, since in source.calls} == {NOW - timedelta(days=180)}


async def test_later_fetch_uses_last_sync_minus_overlap() -> None:
    source = api_source()
    h = await seeded(source)
    codebase = (await h.codebases.list(h.org.id))[0]
    await h.codebases.update(replace(codebase, last_synced_at=NOW - timedelta(days=3)))

    await h.sync()

    assert {since for _, _, since in source.calls} == {NOW - timedelta(days=4)}
    assert (await h.codebases.list(h.org.id))[0].last_synced_at == NOW


async def test_second_sync_writes_nothing() -> None:
    source = api_source(
        pull_requests={"r1": [pr(merged_at=T2)]}, deployments={"r1": [deployment()]}
    )
    h = await seeded(source)
    await h.work_items.add(WorkItem(team_id=h.team_id, title="Dep", key="DEP-1"))

    first = await h.sync()
    second = await h.sync()

    assert first == CodeSyncSummary(h.org.id, 0, 1, 1, 2)
    assert second == CodeSyncSummary(h.org.id, 0, 0, 0, 0)


async def test_deployment_status_change_updates_row() -> None:
    source = api_source(deployments={"r1": [deployment(started_at=RECENT)]})
    h = await seeded(source)
    await h.sync()

    source.deployments = {
        "r1": [deployment(started_at=RECENT, status=DeploymentStatus.SUCCESS, finished_at=RECENT)]
    }
    summary = await h.sync()

    stored = (await h.deployments.get_by_external_ids(["d1"]))["d1"]
    assert stored.status == DeploymentStatus.SUCCESS
    assert stored.finished_at == RECENT
    assert summary.deployments == 1


async def test_pull_request_change_updates_row() -> None:
    source = api_source(pull_requests={"r1": [pr()]})
    h = await seeded(source)
    await h.sync()

    source.pull_requests = {"r1": [pr(title="Fix it", merged_at=RECENT)]}
    summary = await h.sync()

    stored = (await h.pull_requests.get_by_external_ids(["pr12"]))["pr12"]
    assert (stored.title, stored.merged_at) == ("Fix it", RECENT)
    assert summary.pull_requests == 1


async def test_merged_pr_adds_review_and_merged_events() -> None:
    h = await seeded(api_source(pull_requests={"r1": [pr(merged_at=T2)]}))
    item = WorkItem(team_id=h.team_id, title="Dep", key="DEP-1")
    await h.work_items.add(item)

    summary = await h.sync()

    assert summary.events == 2
    assert await h.item_events(item) == [
        (EventType.REVIEW, T1, "acme/api#12"),
        (EventType.MERGED, T2, "acme/api#12"),
    ]


async def test_open_pr_adds_review_only() -> None:
    h = await seeded(api_source(pull_requests={"r1": [pr()]}))
    item = WorkItem(team_id=h.team_id, title="Dep", key="DEP-1")
    await h.work_items.add(item)

    await h.sync()

    assert await h.item_events(item) == [(EventType.REVIEW, T1, "acme/api#12")]


async def test_unknown_keys_link_nothing() -> None:
    source = api_source(pull_requests={"r1": [pr(work_item_keys=("UTF-8", "RELEASE-2026"))]})
    h = await seeded(source)
    await h.work_items.add(WorkItem(team_id=h.team_id, title="Dep", key="DEP-1"))

    summary = await h.sync()

    assert summary.events == 0
    assert summary.pull_requests == 1
    assert len(await h.pull_requests.get_by_external_ids(["pr12"])) == 1


async def test_link_pass_reaches_items_synced_after_the_pr() -> None:
    source = api_source(pull_requests={"r1": [pr(merged_at=T2)]})
    h = await seeded(source)
    await h.sync()
    item = WorkItem(team_id=h.team_id, title="Dep", key="DEP-1")
    await h.work_items.add(item)
    source.pull_requests = {}

    summary = await h.sync()

    assert summary.pull_requests == 0
    assert summary.events == 2
    assert len(await h.item_events(item)) == 2


async def test_link_pass_restores_events_a_rebuild_deleted() -> None:
    h = await seeded(api_source(pull_requests={"r1": [pr(merged_at=T2)]}))
    item = WorkItem(team_id=h.team_id, title="Dep", key="DEP-1")
    await h.work_items.add(item)
    await h.sync()
    before = await h.item_events(item)

    await h.events.delete_sourced_for_work_items([item.id])
    summary = await h.sync()

    assert summary.events == 2
    assert await h.item_events(item) == before


async def test_newly_mapped_codebase_backfills() -> None:
    source = InMemoryCodeHostSource(
        codebases=[
            SourceCodebase(external_id="a", name="acme/a"),
            SourceCodebase(external_id="b", name="acme/b"),
            SourceCodebase(external_id="c", name="acme/c"),
        ]
    )
    h = Harness(source)
    await h.start()
    await h.sync()
    by_name = {c.name: c for c in await h.codebases.list(h.org.id)}
    await h.codebases.update(replace(by_name["acme/a"], team_id=h.team_id))
    await h.sync()
    await h.codebases.update(replace(by_name["acme/b"], team_id=h.team_id))
    source.calls.clear()

    await h.sync()

    sinces = {ext: since for _, ext, since in source.calls}
    assert sinces == {"a": NOW - timedelta(days=1), "b": NOW - timedelta(days=180)}
    stored = {c.name: c for c in await h.codebases.list(h.org.id)}
    assert stored["acme/c"].last_synced_at is None
    assert stored["acme/b"].last_synced_at == NOW


async def test_sync_reports_phases_in_order() -> None:
    h = Harness(api_source())
    await h.start()
    phases: list[SyncPhase] = []

    await h.service.sync(h.org.id, now=NOW, on_phase=phases.append)

    assert phases == [SyncPhase.CODEBASES, SyncPhase.PULL_REQUESTS, SyncPhase.DEPLOYMENTS]


async def test_sync_unknown_organization_raises() -> None:
    h = Harness(api_source())
    with pytest.raises(UnknownOrganizationError):
        await h.service.sync(h.org.id, now=NOW)


async def test_resolve_organization_returns_the_single_one() -> None:
    h = Harness(api_source())
    await h.start()
    assert await h.service.resolve_organization(None) == h.org.id


async def test_resolve_organization_rejects_several() -> None:
    h = Harness(api_source())
    await h.start()
    await h.organizations.add(Organization(name="Other"))
    with pytest.raises(ValueError, match="Multiple organizations"):
        await h.service.resolve_organization(None)


async def test_resolve_organization_without_any_asks_for_linear_first() -> None:
    h = Harness(api_source())
    with pytest.raises(ValueError, match="run a Linear sync first"):
        await h.service.resolve_organization(None)


async def test_link_pass_ignores_work_items_of_other_organizations() -> None:
    h = await seeded(api_source(pull_requests={"r1": [pr()]}))
    other_org = Organization(name="Other")
    other_team = Team(organization_id=other_org.id, name="Elsewhere")
    await h.organizations.add(other_org)
    await h.teams.add(other_team)
    foreign = WorkItem(team_id=other_team.id, title="Dep", key="DEP-1")
    await h.work_items.add(foreign)

    summary = await h.sync()

    assert summary.events == 0
    assert await h.item_events(foreign) == []


async def test_stamp_keeps_edits_made_during_the_fetch() -> None:
    class EditingSource(InMemoryCodeHostSource):
        harness: Harness

        async def fetch_deployments(
            self, codebase_external_id: str, since: datetime
        ) -> list[SourceDeployment]:
            codebase = (await self.harness.codebases.list(self.harness.org.id))[0]
            edited = replace(codebase, team_id=uuid4(), production_environment="prod")
            await self.harness.codebases.update(edited)
            return await super().fetch_deployments(codebase_external_id, since)

    source = EditingSource(codebases=[SourceCodebase(external_id="r1", name="acme/api")])
    h = Harness(source)
    source.harness = h
    await h.start()
    await h.sync()
    await h.map_all()
    original = (await h.codebases.list(h.org.id))[0]

    await h.sync()

    stored = (await h.codebases.list(h.org.id))[0]
    assert stored.team_id != original.team_id
    assert stored.production_environment == "prod"
    assert stored.last_synced_at == NOW


async def test_a_second_organization_leaves_codebases_another_one_owns() -> None:
    source = api_source({"r1": [pr()]})
    h = await seeded(source)
    org_a_codebase = (await h.codebases.list(h.org.id))[0]
    org_b = Organization(name="Beta")
    await h.organizations.add(org_b)
    source.codebases = [SourceCodebase(external_id="r1", name="acme/api-v2")]

    summary = await h.service.sync(org_b.id, now=NOW)

    assert await h.codebases.list(org_b.id) == []
    assert await h.codebases.list(h.org.id) == [replace(org_a_codebase, name="acme/api-v2")]
    assert summary.codebases == 1  # the rename
    assert (summary.pull_requests, summary.deployments, summary.events) == (0, 0, 0)
    assert source.calls == []  # org B fetches only its own mapped codebases


async def test_a_pull_request_returned_twice_is_stored_once_as_its_first_copy() -> None:
    # Updated mid-pagination: it shows up on two pages, the newest copy first.
    h = await seeded(api_source({"r1": [pr(title="Newest"), pr(title="Older")]}))

    summary = await h.sync()

    codebase = (await h.codebases.list(h.org.id))[0]
    stored = await h.pull_requests.list_for_codebases([codebase.id])
    assert [p.title for p in stored] == ["Newest"]
    assert summary.pull_requests == 1
