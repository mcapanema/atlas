from dataclasses import replace
from datetime import UTC, datetime, time
from uuid import uuid4

import pytest

from app.application.sync.service import UnknownOrganizationError
from app.application.sync_schedules.service import (
    DueSync,
    ScheduleSettings,
    SyncScheduleService,
)
from app.domain.organizations.entities import Organization
from app.domain.sync_schedules.entities import SyncRun
from tests.fakes import InMemoryOrganizationRepository, InMemorySyncScheduleRepository

# Wednesday 2026-10-07, 10:30 in São Paulo (UTC-3).
NOW = datetime(2026, 10, 7, 13, 30, tzinfo=UTC)

SETTINGS = ScheduleSettings(
    enabled=True,
    days=frozenset({1, 2, 3, 4, 5}),
    window_start=time(8, 0),
    window_end=time(18, 0),
    interval_minutes=120,
    timezone="America/Sao_Paulo",
)


def _service(
    org: Organization,
    *,
    now: datetime = NOW,
    schedules: InMemorySyncScheduleRepository | None = None,
) -> SyncScheduleService:
    return SyncScheduleService(
        schedules if schedules is not None else InMemorySyncScheduleRepository(),
        InMemoryOrganizationRepository([org]),
        clock=lambda: now,
    )


async def test_unknown_organization_raises() -> None:
    service = _service(Organization(name="Acme"))

    with pytest.raises(UnknownOrganizationError):
        await service.get(uuid4())
    with pytest.raises(UnknownOrganizationError):
        await service.save(uuid4(), SETTINGS)


async def test_no_schedule_reads_as_none() -> None:
    org = Organization(name="Acme")

    assert await _service(org).get(org.id) is None


async def test_save_stamps_updated_at_so_past_slots_never_fire() -> None:
    org = Organization(name="Acme")
    service = _service(org)

    view = await service.save(org.id, SETTINGS)

    assert view.schedule.updated_at == NOW
    # The 10:00 local slot already passed: the next run is 12:00 local.
    assert view.next_run_at == datetime(2026, 10, 7, 15, 0, tzinfo=UTC)
    assert await service.due() == []


async def test_get_reads_back_the_saved_schedule() -> None:
    org = Organization(name="Acme")
    service = _service(org)
    saved = await service.save(org.id, SETTINGS)

    assert await service.get(org.id) == saved


async def test_save_keeps_the_last_run() -> None:
    org = Organization(name="Acme")
    schedules = InMemorySyncScheduleRepository()
    service = _service(org, schedules=schedules)
    await service.save(org.id, SETTINGS)
    await service.record_run(org.id, datetime(2026, 10, 7, 13, 0, tzinfo=UTC), error=None)

    view = await service.save(org.id, SETTINGS)

    assert view.schedule.last_run is not None


async def test_invalid_settings_raise_value_error() -> None:
    org = Organization(name="Acme")

    with pytest.raises(ValueError, match="Unknown timezone"):
        await _service(org).save(
            org.id,
            replace(SETTINGS, timezone="Mars/Base"),
        )


async def test_due_lists_organizations_with_a_pending_slot() -> None:
    org = Organization(name="Acme")
    schedules = InMemorySyncScheduleRepository()
    await _service(org, schedules=schedules).save(org.id, SETTINGS)

    later = _service(org, now=datetime(2026, 10, 7, 15, 1, tzinfo=UTC), schedules=schedules)

    assert await later.due() == [
        DueSync(organization_id=org.id, slot_at=datetime(2026, 10, 7, 15, 0, tzinfo=UTC))
    ]


async def test_record_run_stamps_finished_at_and_consumes_the_slot() -> None:
    org = Organization(name="Acme")
    schedules = InMemorySyncScheduleRepository()
    await _service(org, schedules=schedules).save(org.id, SETTINGS)
    at = datetime(2026, 10, 7, 15, 1, tzinfo=UTC)
    later = _service(org, now=at, schedules=schedules)
    slot = datetime(2026, 10, 7, 15, 0, tzinfo=UTC)

    await later.record_run(org.id, slot, error="boom")

    view = await later.get(org.id)
    assert view is not None
    assert view.schedule.last_run == SyncRun(slot_at=slot, finished_at=at, error="boom")
    assert await later.due() == []


async def test_an_unchanged_resave_keeps_pending_slots_due() -> None:
    # Saved at 10:30 local; the 12:00 slot is due at 12:00:30, and re-saving the
    # same settings before the tick runs it must not cancel it.
    org = Organization(name="Acme")
    schedules = InMemorySyncScheduleRepository()
    await _service(org, schedules=schedules).save(org.id, SETTINGS)
    later = _service(org, now=datetime(2026, 10, 7, 15, 0, 30, tzinfo=UTC), schedules=schedules)

    view = await later.save(org.id, SETTINGS)

    assert view.schedule.updated_at == NOW
    assert [job.slot_at for job in await later.due()] == [datetime(2026, 10, 7, 15, 0, tzinfo=UTC)]


async def test_a_changed_resave_restamps_updated_at() -> None:
    org = Organization(name="Acme")
    schedules = InMemorySyncScheduleRepository()
    await _service(org, schedules=schedules).save(org.id, SETTINGS)
    at = datetime(2026, 10, 7, 15, 0, 30, tzinfo=UTC)

    view = await _service(org, now=at, schedules=schedules).save(
        org.id, replace(SETTINGS, interval_minutes=60)
    )

    assert view.schedule.updated_at == at


async def test_record_manual_sync_covers_the_next_slot() -> None:
    org = Organization(name="Acme")
    schedules = InMemorySyncScheduleRepository()
    await _service(org, schedules=schedules).save(org.id, SETTINGS)
    # Sync now at 11:50 local, ten minutes before the 12:00 slot.
    before_slot = _service(org, now=datetime(2026, 10, 7, 14, 50, tzinfo=UTC), schedules=schedules)

    await before_slot.record_manual_sync(org.id)

    view = await before_slot.get(org.id)
    assert view is not None
    assert view.schedule.last_manual_sync_at == datetime(2026, 10, 7, 14, 50, tzinfo=UTC)
    assert view.next_run_at == datetime(2026, 10, 7, 17, 0, tzinfo=UTC)  # 14:00 local


async def test_save_keeps_the_last_manual_sync() -> None:
    org = Organization(name="Acme")
    schedules = InMemorySyncScheduleRepository()
    service = _service(org, schedules=schedules)
    await service.save(org.id, SETTINGS)
    await service.record_manual_sync(org.id)

    view = await service.save(org.id, replace(SETTINGS, interval_minutes=60))

    assert view.schedule.last_manual_sync_at == NOW
