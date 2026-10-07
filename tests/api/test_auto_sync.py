import asyncio
from datetime import UTC, datetime, time
from unittest import mock
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.auto_sync import AutoSyncRunner
from app.api.deps import LINEAR_NOT_CONFIGURED
from app.domain._time import utcnow
from app.domain.organizations.entities import Organization
from app.domain.sync.port import DataSourceError
from app.domain.sync.source import SourceTeam
from app.domain.sync_schedules.entities import SyncRun, SyncSchedule
from app.infrastructure.repositories.organizations import SqlAlchemyOrganizationRepository
from app.infrastructure.repositories.sync_schedules import SqlAlchemySyncScheduleRepository
from app.infrastructure.repositories.teams import SqlAlchemyTeamRepository
from tests.fakes import FakeDataSource

LONG_AGO = datetime(2020, 1, 1, tzinfo=UTC)


def _source() -> FakeDataSource:
    return FakeDataSource(teams=[SourceTeam(external_id="lt1", name="Platform")])


class _FailingSource(FakeDataSource):
    async def fetch_teams(self) -> list[SourceTeam]:
        raise DataSourceError("boom")


async def _seed(
    sessionmaker: async_sessionmaker[AsyncSession],
    *,
    enabled: bool = True,
    updated_at: datetime = LONG_AGO,
) -> UUID:
    """An organization whose schedule has a slot every 15 min, all day, every day."""
    org = Organization(name="Acme")
    async with sessionmaker() as session:
        await SqlAlchemyOrganizationRepository(session).add(org)
        await SqlAlchemySyncScheduleRepository(session).save(
            SyncSchedule(
                organization_id=org.id,
                enabled=enabled,
                days=frozenset(range(1, 8)),
                window_start=time(0, 0),
                window_end=time(23, 45),
                interval_minutes=15,
                timezone="UTC",
                updated_at=updated_at,
            )
        )
        await session.commit()
    return org.id


async def _last_run(
    sessionmaker: async_sessionmaker[AsyncSession], organization_id: UUID
) -> SyncRun | None:
    async with sessionmaker() as session:
        schedule = await SqlAlchemySyncScheduleRepository(session).get(organization_id)
    assert schedule is not None
    return schedule.last_run


async def test_tick_syncs_a_due_organization_and_records_success(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    org_id = await _seed(sessionmaker)
    runner = AutoSyncRunner(sessionmaker, _source)

    assert await runner.tick() == 1

    async with sessionmaker() as session:
        teams = await SqlAlchemyTeamRepository(session).list()
    assert [(team.name, team.organization_id) for team in teams] == [("Platform", org_id)]
    run = await _last_run(sessionmaker, org_id)
    assert run is not None
    assert run.error is None
    assert await runner.tick() == 0  # the slot is consumed


async def test_tick_records_failure_and_does_not_retry_the_slot(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    org_id = await _seed(sessionmaker)
    runner = AutoSyncRunner(sessionmaker, _FailingSource)

    assert await runner.tick() == 1

    run = await _last_run(sessionmaker, org_id)
    assert run is not None
    assert run.error == "boom"
    assert await runner.tick() == 0


async def test_tick_records_unconfigured_connector(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    org_id = await _seed(sessionmaker)
    runner = AutoSyncRunner(sessionmaker, lambda: None)

    assert await runner.tick() == 1

    run = await _last_run(sessionmaker, org_id)
    assert run is not None
    assert run.error == LINEAR_NOT_CONFIGURED
    assert await runner.tick() == 0


async def test_tick_skips_disabled_and_just_saved_schedules(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    await _seed(sessionmaker, enabled=False)
    await _seed(sessionmaker, updated_at=utcnow())  # latest slot predates the save
    runner = AutoSyncRunner(sessionmaker, _source)

    assert await runner.tick() == 0


async def test_tick_skips_while_a_sync_holds_the_lock(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    org_id = await _seed(sessionmaker)
    runner = AutoSyncRunner(sessionmaker, _source)

    async with runner.lock:  # a manual sync is running
        assert await runner.tick() == 0
    assert await _last_run(sessionmaker, org_id) is None  # slot still pending

    assert await runner.tick() == 1


async def test_start_ticks_at_once_so_a_missed_slot_catches_up(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    runner = AutoSyncRunner(sessionmaker, _source, tick_seconds=3600)
    with mock.patch.object(AutoSyncRunner, "tick", autospec=True, return_value=0) as tick:
        runner.start()
        await asyncio.sleep(0)

        tick.assert_awaited_once()
        assert runner.running
        await runner.close()

    assert not runner.running


async def test_loop_survives_a_failing_tick(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    runner = AutoSyncRunner(sessionmaker, _source, tick_seconds=0)
    with mock.patch.object(
        AutoSyncRunner, "tick", autospec=True, side_effect=[RuntimeError("db down"), 0, 0, 0]
    ) as tick:
        runner.start()
        for _ in range(5):
            await asyncio.sleep(0)
        await runner.close()

    assert tick.await_count >= 2
