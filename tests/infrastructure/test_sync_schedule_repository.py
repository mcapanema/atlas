from dataclasses import replace
from datetime import UTC, datetime, time
from typing import Any
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.sync_schedules.entities import SyncRun, SyncSchedule
from app.infrastructure.repositories.sync_schedules import SqlAlchemySyncScheduleRepository


def _schedule(**changes: Any) -> SyncSchedule:
    base = SyncSchedule(
        organization_id=uuid4(),
        enabled=True,
        days=frozenset({1, 3, 5}),
        window_start=time(8, 0),
        window_end=time(18, 30),
        interval_minutes=90,
        timezone="America/Sao_Paulo",
        updated_at=datetime(2026, 10, 7, 12, 0, tzinfo=UTC),
    )
    return replace(base, **changes)


async def test_save_then_get_round_trips_through_the_database(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    schedule = _schedule()
    async with sessionmaker() as session:
        await SqlAlchemySyncScheduleRepository(session).save(schedule)
        await session.commit()

    async with sessionmaker() as session:  # fresh session: no identity-map shortcut
        loaded = await SqlAlchemySyncScheduleRepository(session).get(schedule.organization_id)

    assert loaded == schedule
    assert loaded is not None
    assert loaded.updated_at.tzinfo is not None


async def test_get_unknown_organization_is_none(session: AsyncSession) -> None:
    assert await SqlAlchemySyncScheduleRepository(session).get(uuid4()) is None


async def test_record_run_writes_only_the_last_run(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    schedule = _schedule()
    run = SyncRun(
        slot_at=datetime(2026, 10, 7, 13, 0, tzinfo=UTC),
        finished_at=datetime(2026, 10, 7, 13, 2, tzinfo=UTC),
        error="boom",
    )
    async with sessionmaker() as session:
        repository = SqlAlchemySyncScheduleRepository(session)
        await repository.save(schedule)
        await repository.record_run(schedule.organization_id, run)
        await session.commit()

    async with sessionmaker() as session:
        loaded = await SqlAlchemySyncScheduleRepository(session).get(schedule.organization_id)

    assert loaded == replace(schedule, last_run=run)


async def test_save_on_an_existing_schedule_keeps_its_last_run(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    schedule = _schedule()
    run = SyncRun(
        slot_at=datetime(2026, 10, 7, 13, 0, tzinfo=UTC),
        finished_at=datetime(2026, 10, 7, 13, 1, tzinfo=UTC),
    )
    edited = replace(schedule, enabled=False, interval_minutes=60)  # last_run None
    async with sessionmaker() as session:
        repository = SqlAlchemySyncScheduleRepository(session)
        await repository.save(schedule)
        await repository.record_run(schedule.organization_id, run)
        await repository.save(edited)
        await session.commit()

    async with sessionmaker() as session:
        loaded = await SqlAlchemySyncScheduleRepository(session).get(schedule.organization_id)

    assert loaded == replace(edited, last_run=run)


async def test_record_run_without_a_schedule_is_a_no_op(session: AsyncSession) -> None:
    repository = SqlAlchemySyncScheduleRepository(session)
    now = datetime(2026, 10, 7, tzinfo=UTC)

    await repository.record_run(uuid4(), SyncRun(slot_at=now, finished_at=now))

    assert await repository.list_enabled() == []


async def test_list_enabled_skips_disabled_schedules(session: AsyncSession) -> None:
    repository = SqlAlchemySyncScheduleRepository(session)
    on = _schedule()
    await repository.save(on)
    await repository.save(_schedule(enabled=False))

    assert await repository.list_enabled() == [on]
