from datetime import date, datetime
from uuid import UUID

from sqlalchemy import Date, Float, Integer, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.domain.snapshots.entities import ForecastSnapshot, MetricSnapshot
from app.infrastructure.database.base import Base
from app.infrastructure.database.types import UTCDateTime


class MetricSnapshotModel(Base):
    __tablename__ = "metric_snapshots"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    team_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    project_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    captured_on: Mapped[date] = mapped_column(Date, nullable=False)
    window_days: Mapped[int] = mapped_column(Integer, nullable=False)
    completed: Mapped[int] = mapped_column(Integer, nullable=False)
    wip: Mapped[int] = mapped_column(Integer, nullable=False)
    lead_time_p50_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    lead_time_p85_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    cycle_time_p50_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    cycle_time_p85_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    blocked_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    flow_efficiency: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)

    def to_domain(self) -> MetricSnapshot:
        return MetricSnapshot(
            id=self.id,
            team_id=self.team_id,
            project_id=self.project_id,
            captured_on=self.captured_on,
            window_days=self.window_days,
            completed=self.completed,
            wip=self.wip,
            lead_time_p50_seconds=self.lead_time_p50_seconds,
            lead_time_p85_seconds=self.lead_time_p85_seconds,
            cycle_time_p50_seconds=self.cycle_time_p50_seconds,
            cycle_time_p85_seconds=self.cycle_time_p85_seconds,
            blocked_seconds=self.blocked_seconds,
            flow_efficiency=self.flow_efficiency,
            created_at=self.created_at,
        )

    @classmethod
    def from_domain(cls, snapshot: MetricSnapshot) -> "MetricSnapshotModel":
        return cls(
            id=snapshot.id,
            team_id=snapshot.team_id,
            project_id=snapshot.project_id,
            captured_on=snapshot.captured_on,
            window_days=snapshot.window_days,
            completed=snapshot.completed,
            wip=snapshot.wip,
            lead_time_p50_seconds=snapshot.lead_time_p50_seconds,
            lead_time_p85_seconds=snapshot.lead_time_p85_seconds,
            cycle_time_p50_seconds=snapshot.cycle_time_p50_seconds,
            cycle_time_p85_seconds=snapshot.cycle_time_p85_seconds,
            blocked_seconds=snapshot.blocked_seconds,
            flow_efficiency=snapshot.flow_efficiency,
            created_at=snapshot.created_at,
        )


class ForecastSnapshotModel(Base):
    __tablename__ = "forecast_snapshots"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    team_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    project_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    captured_on: Mapped[date] = mapped_column(Date, nullable=False)
    window_days: Mapped[int] = mapped_column(Integer, nullable=False)
    remaining: Mapped[int] = mapped_column(Integer, nullable=False)
    p50_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    p85_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)

    def to_domain(self) -> ForecastSnapshot:
        return ForecastSnapshot(
            id=self.id,
            team_id=self.team_id,
            project_id=self.project_id,
            captured_on=self.captured_on,
            window_days=self.window_days,
            remaining=self.remaining,
            p50_days=self.p50_days,
            p85_days=self.p85_days,
            created_at=self.created_at,
        )

    @classmethod
    def from_domain(cls, snapshot: ForecastSnapshot) -> "ForecastSnapshotModel":
        return cls(
            id=snapshot.id,
            team_id=snapshot.team_id,
            project_id=snapshot.project_id,
            captured_on=snapshot.captured_on,
            window_days=snapshot.window_days,
            remaining=snapshot.remaining,
            p50_days=snapshot.p50_days,
            p85_days=snapshot.p85_days,
            created_at=snapshot.created_at,
        )


class SqlAlchemyMetricSnapshotRepository:
    """SQLAlchemy adapter for the MetricSnapshotRepository port."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, snapshot: MetricSnapshot) -> None:
        self._session.add(MetricSnapshotModel.from_domain(snapshot))
        await self._session.flush()

    async def list(
        self, *, team_id: UUID | None = None, project_id: UUID | None = None
    ) -> list[MetricSnapshot]:
        stmt = select(MetricSnapshotModel).order_by(MetricSnapshotModel.captured_on)
        if team_id is not None:
            stmt = stmt.where(MetricSnapshotModel.team_id == team_id)
        if project_id is not None:
            stmt = stmt.where(MetricSnapshotModel.project_id == project_id)
        result = await self._session.execute(stmt)
        return [model.to_domain() for model in result.scalars()]

    async def exists_on(
        self,
        captured_on: date,
        *,
        team_id: UUID | None = None,
        project_id: UUID | None = None,
    ) -> bool:
        stmt = select(MetricSnapshotModel.id).where(
            MetricSnapshotModel.captured_on == captured_on
        )
        if team_id is not None:
            stmt = stmt.where(MetricSnapshotModel.team_id == team_id)
        if project_id is not None:
            stmt = stmt.where(MetricSnapshotModel.project_id == project_id)
        result = await self._session.execute(stmt.limit(1))
        return result.scalars().first() is not None


class SqlAlchemyForecastSnapshotRepository:
    """SQLAlchemy adapter for the ForecastSnapshotRepository port."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, snapshot: ForecastSnapshot) -> None:
        self._session.add(ForecastSnapshotModel.from_domain(snapshot))
        await self._session.flush()

    async def list(
        self, *, team_id: UUID | None = None, project_id: UUID | None = None
    ) -> list[ForecastSnapshot]:
        stmt = select(ForecastSnapshotModel).order_by(ForecastSnapshotModel.captured_on)
        if team_id is not None:
            stmt = stmt.where(ForecastSnapshotModel.team_id == team_id)
        if project_id is not None:
            stmt = stmt.where(ForecastSnapshotModel.project_id == project_id)
        result = await self._session.execute(stmt)
        return [model.to_domain() for model in result.scalars()]

    async def exists_on(
        self,
        captured_on: date,
        *,
        team_id: UUID | None = None,
        project_id: UUID | None = None,
    ) -> bool:
        stmt = select(ForecastSnapshotModel.id).where(
            ForecastSnapshotModel.captured_on == captured_on
        )
        if team_id is not None:
            stmt = stmt.where(ForecastSnapshotModel.team_id == team_id)
        if project_id is not None:
            stmt = stmt.where(ForecastSnapshotModel.project_id == project_id)
        result = await self._session.execute(stmt.limit(1))
        return result.scalars().first() is not None
