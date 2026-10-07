"""Use cases for an organization's auto-sync schedule (ADR-0014)."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, time
from uuid import UUID

from app.application.sync.service import UnknownOrganizationError
from app.domain._time import utcnow
from app.domain.organizations.repository import OrganizationRepository
from app.domain.sync_schedules.entities import SyncRun, SyncSchedule
from app.domain.sync_schedules.repository import SyncScheduleRepository
from app.domain.sync_schedules.slots import due_slot, next_slot


@dataclass(frozen=True)
class ScheduleSettings:
    """The user-editable part of a schedule: everything but its run history."""

    enabled: bool
    days: frozenset[int]
    window_start: time
    window_end: time
    interval_minutes: int
    timezone: str


@dataclass(frozen=True)
class SyncScheduleView:
    schedule: SyncSchedule
    # None while auto sync is off.
    next_run_at: datetime | None


@dataclass(frozen=True)
class DueSync:
    organization_id: UUID
    # The scheduled instant this run satisfies (recorded as SyncRun.slot_at).
    slot_at: datetime


class SyncScheduleService:
    """Reads and edits schedules, and tells the auto-sync runner what is due."""

    def __init__(
        self,
        schedules: SyncScheduleRepository,
        organizations: OrganizationRepository,
        clock: Callable[[], datetime] = utcnow,
    ) -> None:
        self._schedules = schedules
        self._organizations = organizations
        self._clock = clock

    async def get(self, organization_id: UUID) -> SyncScheduleView | None:
        await self._require(organization_id)
        schedule = await self._schedules.get(organization_id)
        return self._view(schedule) if schedule is not None else None

    async def save(self, organization_id: UUID, settings: ScheduleSettings) -> SyncScheduleView:
        await self._require(organization_id)
        existing = await self._schedules.get(organization_id)
        schedule = SyncSchedule(
            organization_id=organization_id,
            enabled=settings.enabled,
            days=settings.days,
            window_start=settings.window_start,
            window_end=settings.window_end,
            interval_minutes=settings.interval_minutes,
            timezone=settings.timezone,
            # Slots at or before this save never fire: saving at 10:05 does
            # not trigger a run for 10:00.
            updated_at=self._clock(),
            last_run=existing.last_run if existing is not None else None,
        )
        await self._schedules.save(schedule)
        return self._view(schedule)

    async def due(self) -> list[DueSync]:
        now = self._clock()
        return [
            DueSync(organization_id=schedule.organization_id, slot_at=slot)
            for schedule in await self._schedules.list_enabled()
            if (slot := due_slot(schedule, now)) is not None
        ]

    async def record_run(
        self, organization_id: UUID, slot_at: datetime, *, error: str | None
    ) -> None:
        run = SyncRun(slot_at=slot_at, finished_at=self._clock(), error=error)
        await self._schedules.record_run(organization_id, run)

    def _view(self, schedule: SyncSchedule) -> SyncScheduleView:
        return SyncScheduleView(schedule=schedule, next_run_at=next_slot(schedule, self._clock()))

    async def _require(self, organization_id: UUID) -> None:
        if await self._organizations.get(organization_id) is None:
            raise UnknownOrganizationError(f"Organization {organization_id} does not exist")
