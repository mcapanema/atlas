from datetime import datetime, time
from uuid import UUID

from sqlalchemy import JSON, Boolean, Integer, String, Text, Time, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.domain.sync_schedules.entities import SyncRun, SyncSchedule
from app.infrastructure.database.base import Base
from app.infrastructure.database.types import UTCDateTime


class SyncScheduleModel(Base):
    __tablename__ = "sync_schedules"

    # One schedule per organization. ponytail: no FK to organizations, same
    # as teams.organization_id.
    organization_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    # Sorted ISO weekdays (1 = Monday … 7 = Sunday).
    days: Mapped[list[int]] = mapped_column(JSON, nullable=False)
    window_start: Mapped[time] = mapped_column(Time, nullable=False)
    window_end: Mapped[time] = mapped_column(Time, nullable=False)
    interval_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    # The last run; written only by record_run (the auto-sync runner).
    last_slot_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    last_finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    def to_domain(self) -> SyncSchedule:
        last_run = None
        if self.last_slot_at is not None and self.last_finished_at is not None:
            last_run = SyncRun(
                slot_at=self.last_slot_at,
                finished_at=self.last_finished_at,
                error=self.last_error,
            )
        return SyncSchedule(
            organization_id=self.organization_id,
            enabled=self.enabled,
            days=frozenset(self.days),
            window_start=self.window_start,
            window_end=self.window_end,
            interval_minutes=self.interval_minutes,
            timezone=self.timezone,
            updated_at=self.updated_at,
            last_run=last_run,
        )

    @classmethod
    def from_domain(cls, schedule: SyncSchedule) -> "SyncScheduleModel":
        model = cls(organization_id=schedule.organization_id)
        model.set_settings(schedule)
        model.set_run(schedule.last_run)
        return model

    def set_settings(self, schedule: SyncSchedule) -> None:
        self.enabled = schedule.enabled
        self.days = sorted(schedule.days)
        self.window_start = schedule.window_start
        self.window_end = schedule.window_end
        self.interval_minutes = schedule.interval_minutes
        self.timezone = schedule.timezone
        self.updated_at = schedule.updated_at

    def set_run(self, run: SyncRun | None) -> None:
        self.last_slot_at = run.slot_at if run is not None else None
        self.last_finished_at = run.finished_at if run is not None else None
        self.last_error = run.error if run is not None else None


class SqlAlchemySyncScheduleRepository:
    """SQLAlchemy adapter for the SyncScheduleRepository port."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, organization_id: UUID) -> SyncSchedule | None:
        model = await self._session.get(SyncScheduleModel, organization_id)
        return model.to_domain() if model is not None else None

    async def list_enabled(self) -> list[SyncSchedule]:
        result = await self._session.execute(
            select(SyncScheduleModel)
            .where(SyncScheduleModel.enabled)
            .order_by(SyncScheduleModel.organization_id)
        )
        return [model.to_domain() for model in result.scalars()]

    async def save(self, schedule: SyncSchedule) -> None:
        # An existing row keeps its last_* columns: the auto-sync runner owns
        # them (record_run), so a settings edit can't erase a run's outcome.
        existing = await self._session.get(SyncScheduleModel, schedule.organization_id)
        if existing is None:
            self._session.add(SyncScheduleModel.from_domain(schedule))
        else:
            existing.set_settings(schedule)
        await self._session.flush()

    async def record_run(self, organization_id: UUID, run: SyncRun) -> None:
        existing = await self._session.get(SyncScheduleModel, organization_id)
        if existing is None:
            return
        existing.set_run(run)
        await self._session.flush()
