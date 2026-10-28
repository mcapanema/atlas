import asyncio
from datetime import UTC, datetime, time
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.deps import metric_rules_service_for
from app.api.recompute import RecomputeRunner
from app.api.sync_jobs import (
    HISTORY_SIZE,
    SyncBusyError,
    SyncJobRequest,
    SyncJobRunner,
    covers,
)
from app.application.sync.service import SyncPhase
from app.domain.events.entities import EventType
from app.domain.organizations.entities import Organization
from app.domain.sync.port import DataSourceError
from app.domain.sync.source import SourceEvent, SourceTeam, SourceWorkItem
from app.domain.sync_schedules.entities import SyncSchedule
from app.domain.teams.entities import Team
from app.domain.work_items.entities import WorkItemType
from app.infrastructure.repositories.organizations import SqlAlchemyOrganizationRepository
from app.infrastructure.repositories.sync_schedules import SqlAlchemySyncScheduleRepository
from app.infrastructure.repositories.teams import SqlAlchemyTeamRepository
from tests.fakes import FakeDataSource

OCCURRED = datetime(2026, 7, 1, 10, 0, tzinfo=UTC)


def _source() -> FakeDataSource:
    return FakeDataSource(
        teams=[SourceTeam(external_id="lt1", name="Platform")],
        work_items=[
            SourceWorkItem(
                external_id="li1",
                title="Fix login",
                type=WorkItemType.TASK,
                state="In Progress",
                team_external_id="lt1",
                project_external_id=None,
                created_at=OCCURRED,
                events=(
                    SourceEvent(
                        external_id="li1:created", type=EventType.CREATED, occurred_at=OCCURRED
                    ),
                ),
            )
        ],
    )


class _BlockingSource(FakeDataSource):
    """Holds the sync inside fetch_work_items until `release`; sets `entered` on arrival."""

    def __init__(self) -> None:
        super().__init__(teams=[SourceTeam(external_id="lt1", name="Platform")])
        self.entered = asyncio.Event()
        self.release = asyncio.Event()

    async def fetch_work_items(self, team_external_id: str | None = None) -> list[SourceWorkItem]:
        self.entered.set()
        await self.release.wait()
        return await super().fetch_work_items(team_external_id)


class _FailingSource(FakeDataSource):
    def __init__(self) -> None:
        super().__init__(teams=[SourceTeam(external_id="lt1", name="Platform")])

    async def fetch_work_items(self, team_external_id: str | None = None) -> list[SourceWorkItem]:
        raise DataSourceError("Linear is down")


async def _seed_org(
    sessionmaker: async_sessionmaker[AsyncSession], *, schedule: bool = False
) -> UUID:
    org = Organization(name="Acme")
    async with sessionmaker() as session:
        await SqlAlchemyOrganizationRepository(session).add(org)
        if schedule:
            await SqlAlchemySyncScheduleRepository(session).save(
                SyncSchedule(
                    organization_id=org.id,
                    enabled=True,
                    days=frozenset(range(1, 8)),
                    window_start=time(0, 0),
                    window_end=time(23, 45),
                    interval_minutes=15,
                    timezone="UTC",
                    updated_at=OCCURRED,
                )
            )
        await session.commit()
    return org.id


async def _teams(sessionmaker: async_sessionmaker[AsyncSession]) -> list[Team]:
    async with sessionmaker() as session:
        return await SqlAlchemyTeamRepository(session).list()


async def _last_manual_sync_at(
    sessionmaker: async_sessionmaker[AsyncSession], organization_id: UUID
) -> datetime | None:
    async with sessionmaker() as session:
        schedule = await SqlAlchemySyncScheduleRepository(session).get(organization_id)
    assert schedule is not None
    return schedule.last_manual_sync_at


def _runner(
    sessionmaker: async_sessionmaker[AsyncSession], recompute: RecomputeRunner | None = None
) -> SyncJobRunner:
    return SyncJobRunner(sessionmaker, recompute=recompute or RecomputeRunner(sessionmaker))


def test_covers_matrix() -> None:
    org = uuid4()
    team = uuid4()
    plain = SyncJobRequest(org, "organization", "auto")
    assert covers(plain, SyncJobRequest(org, "organization", "manual"))
    assert covers(plain, SyncJobRequest(org, "team", "manual", team_id=team))
    assert not covers(plain, SyncJobRequest(org, "organization", "manual", rebuild=True))
    assert covers(SyncJobRequest(org, "organization", "manual", rebuild=True), plain)
    assert not covers(SyncJobRequest(org, "team", "manual", team_id=team), plain)
    assert not covers(plain, SyncJobRequest(uuid4(), "organization", "manual"))
    same_team = SyncJobRequest(org, "team", "manual", team_id=team)
    assert covers(same_team, SyncJobRequest(org, "team", "auto", team_id=team))
    assert not covers(same_team, SyncJobRequest(org, "team", "manual", team_id=uuid4()))


def test_a_team_request_names_its_team_and_only_a_team_request_does() -> None:
    with pytest.raises(ValueError, match="team_id"):
        SyncJobRequest(uuid4(), "team", "manual")
    with pytest.raises(ValueError, match="team_id"):
        SyncJobRequest(uuid4(), "organization", "manual", team_id=uuid4())


async def test_start_returns_at_once_and_the_job_succeeds_with_a_summary(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    org_id = await _seed_org(sessionmaker)
    runner = _runner(sessionmaker)

    job = runner.start(SyncJobRequest(org_id, "organization", "manual"), _source())

    started_state = job.state
    assert started_state == "running"
    assert runner.running is job
    assert runner.get(job.id) is job
    await runner.wait_idle()
    assert job.state == "succeeded"
    assert job.summary is not None
    assert job.summary.work_items == 1
    assert job.phase == SyncPhase.SNAPSHOTS
    assert job.finished_at is not None
    assert job.error is None
    assert [t.name for t in await _teams(sessionmaker)] == ["Platform"]


async def test_team_job_runs_the_team_sync(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    org_id = await _seed_org(sessionmaker)
    runner = _runner(sessionmaker)
    runner.start(SyncJobRequest(org_id, "organization", "manual"), _source())
    await runner.wait_idle()
    (team,) = await _teams(sessionmaker)

    job = runner.start(SyncJobRequest(org_id, "team", "manual", team_id=team.id), _source())
    await runner.wait_idle()

    assert job.state == "succeeded"
    assert job.summary is not None
    assert job.summary.organization_id == org_id
    assert job.summary.teams == 0  # a team sync doesn't sync the team list
    assert job.phase == SyncPhase.SNAPSHOTS


async def test_start_returns_the_running_job_when_it_covers_the_request(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    org_id = await _seed_org(sessionmaker)
    runner = _runner(sessionmaker)
    source = _BlockingSource()

    first = runner.start(SyncJobRequest(org_id, "organization", "auto"), source)
    again = runner.start(SyncJobRequest(org_id, "team", "manual", team_id=uuid4()), source)

    assert again is first
    source.release.set()
    await runner.wait_idle()
    assert first.state == "succeeded"


async def test_start_raises_busy_for_a_request_the_running_job_does_not_cover(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    org_id = await _seed_org(sessionmaker)
    runner = _runner(sessionmaker)
    source = _BlockingSource()

    first = runner.start(SyncJobRequest(org_id, "organization", "auto"), source)
    with pytest.raises(SyncBusyError) as busy:
        runner.start(SyncJobRequest(org_id, "organization", "manual", rebuild=True), source)

    assert busy.value.job is first
    source.release.set()
    await runner.wait_idle()


async def test_a_failed_job_rolls_back_and_releases_the_lock(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    org_id = await _seed_org(sessionmaker)
    runner = _runner(sessionmaker)

    job = runner.start(SyncJobRequest(org_id, "organization", "manual"), _FailingSource())
    await runner.wait_idle()

    assert job.state == "failed"
    assert job.error == "Linear is down"
    assert job.finished_at is not None
    assert not runner.lock.locked()
    assert runner.running is None
    assert await _teams(sessionmaker) == []  # nothing from the failed run committed


async def test_an_unexpected_error_fails_the_job_with_its_type_name(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    org_id = await _seed_org(sessionmaker)

    class Buggy(FakeDataSource):
        async def fetch_teams(self) -> list[SourceTeam]:
            raise RuntimeError

    runner = _runner(sessionmaker)
    job = runner.start(SyncJobRequest(org_id, "organization", "manual"), Buggy())
    await runner.wait_idle()

    assert job.state == "failed"
    assert job.error == "RuntimeError"


async def test_manual_org_job_records_the_manual_sync_only_on_success(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    org_id = await _seed_org(sessionmaker, schedule=True)
    runner = _runner(sessionmaker)

    runner.start(SyncJobRequest(org_id, "organization", "manual"), _FailingSource())
    await runner.wait_idle()
    assert await _last_manual_sync_at(sessionmaker, org_id) is None

    runner.start(SyncJobRequest(org_id, "organization", "auto"), _source())
    await runner.wait_idle()
    assert await _last_manual_sync_at(sessionmaker, org_id) is None

    (team,) = await _teams(sessionmaker)
    runner.start(SyncJobRequest(org_id, "team", "manual", team_id=team.id), _source())
    await runner.wait_idle()
    assert await _last_manual_sync_at(sessionmaker, org_id) is None

    runner.start(SyncJobRequest(org_id, "organization", "manual"), _source())
    await runner.wait_idle()
    assert await _last_manual_sync_at(sessionmaker, org_id) is not None


async def test_rebuild_job_queues_history_recompute(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    org_id = await _seed_org(sessionmaker)
    recompute = RecomputeRunner(sessionmaker)
    runner = _runner(sessionmaker, recompute)

    job = runner.start(SyncJobRequest(org_id, "organization", "manual", rebuild=True), _source())
    await runner.wait_idle()
    await recompute.wait_idle()

    assert job.state == "succeeded"
    async with sessionmaker() as session:
        view = await metric_rules_service_for(session).organization_view(org_id)
    assert view is not None
    assert view.recompute.state == "idle"
    assert view.recompute.finished_at is not None  # history was rewritten


async def test_a_plain_job_does_not_recompute_history(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    org_id = await _seed_org(sessionmaker)
    recompute = RecomputeRunner(sessionmaker)
    runner = _runner(sessionmaker, recompute)

    runner.start(SyncJobRequest(org_id, "organization", "manual"), _source())
    await runner.wait_idle()
    await recompute.wait_idle()

    async with sessionmaker() as session:
        view = await metric_rules_service_for(session).organization_view(org_id)
    assert view is not None
    assert view.recompute.finished_at is None


async def test_job_runs_with_the_recompute_runner_paused(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    # A history recompute holds SQLite's write lock while it rewrites a scope.
    org_id = await _seed_org(sessionmaker)
    recompute = RecomputeRunner(sessionmaker)
    paused: list[bool] = []

    class Probe(FakeDataSource):
        async def fetch_teams(self) -> list[SourceTeam]:
            paused.append(recompute._lock.locked())  # held for a paused() body
            return await super().fetch_teams()

    runner = _runner(sessionmaker, recompute)
    runner.start(SyncJobRequest(org_id, "organization", "manual"), Probe())
    await runner.wait_idle()

    assert paused == [True]
    assert not recompute._lock.locked()


async def test_run_waits_for_the_running_job_then_runs_to_completion(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    org_id = await _seed_org(sessionmaker)
    runner = _runner(sessionmaker)
    source = _BlockingSource()
    first = runner.start(SyncJobRequest(org_id, "organization", "manual"), source)

    waiting = asyncio.create_task(
        runner.run(SyncJobRequest(org_id, "organization", "auto"), _source())
    )
    await asyncio.sleep(0)
    assert runner.running is first
    source.release.set()
    second = await waiting

    assert first.state == "succeeded"
    assert second is not first
    assert second.state == "succeeded"
    assert runner.get(second.id) is second


async def test_cancelling_a_waiting_run_leaves_the_running_job_alone(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    # Auto sync's loop waits in run() behind a manual job; closing it must not
    # cancel (and roll back) that manual job.
    org_id = await _seed_org(sessionmaker)
    runner = _runner(sessionmaker)
    source = _BlockingSource()
    first = runner.start(SyncJobRequest(org_id, "organization", "manual"), source)

    waiter = asyncio.create_task(
        runner.run(SyncJobRequest(org_id, "organization", "auto"), _source())
    )
    await asyncio.sleep(0)
    waiter.cancel()
    await asyncio.gather(waiter, return_exceptions=True)
    source.release.set()
    await runner.wait_idle()

    assert waiter.cancelled()
    assert first.state == "succeeded"


async def test_run_returns_a_failed_job_without_raising(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    org_id = await _seed_org(sessionmaker)
    runner = _runner(sessionmaker)

    job = await runner.run(SyncJobRequest(org_id, "organization", "auto"), _FailingSource())

    assert job.state == "failed"
    assert job.error == "Linear is down"


async def test_close_cancels_the_running_job_and_rolls_it_back(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    org_id = await _seed_org(sessionmaker)
    runner = _runner(sessionmaker)
    source = _BlockingSource()
    job = runner.start(SyncJobRequest(org_id, "organization", "manual"), source)
    # Cancel only once the job waits on the source: a cancel mid-query would break
    # the fixture's single StaticPool connection and drop the in-memory schema.
    await source.entered.wait()

    await runner.close()

    assert job.state == "running"  # a cancel writes no finish state
    assert job.finished_at is None
    assert runner.running is None
    assert not runner.lock.locked()
    assert await _teams(sessionmaker) == []


async def test_close_before_the_job_starts_frees_the_runner(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    org_id = await _seed_org(sessionmaker)
    runner = _runner(sessionmaker)
    request = SyncJobRequest(org_id, "organization", "manual")
    cancelled = runner.start(request, _source())

    await runner.close()  # the task never ran a step

    assert cancelled.state == "running"
    assert runner.running is None
    job = await runner.run(request, _source())
    assert job.state == "succeeded"


async def test_history_keeps_the_last_twenty_jobs(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    org_id = await _seed_org(sessionmaker)
    runner = _runner(sessionmaker)
    request = SyncJobRequest(org_id, "organization", "auto")

    jobs = []
    for _ in range(HISTORY_SIZE + 1):
        jobs.append(runner.start(request, FakeDataSource()))
        await runner.wait_idle()

    assert HISTORY_SIZE == 20
    assert runner.get(jobs[0].id) is None
    assert runner.get(jobs[1].id) is jobs[1]
    assert runner.get(jobs[-1].id) is jobs[-1]
