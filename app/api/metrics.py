from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, tzinfo
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import MetricsServiceDep, SnapshotServiceDep
from app.api.schemas import (
    AgingItemRead,
    AgingWipRead,
    DeliveryHealthRead,
    DurationStatsRead,
    FlowHistoryRead,
    FlowMetricsRead,
    LeadTimeDistributionRead,
    MetricSnapshotRead,
)
from app.api.scope import ItemFiltersDep, ScopeDep
from app.domain.metrics.summary import DurationStats

router = APIRouter(prefix="/api/metrics", tags=["metrics"])


@dataclass(frozen=True)
class Period:
    """An explicit start/end analysis window (both dates inclusive), or none.

    Resolved against the scope's timezone: `now` is the local midnight after
    `end`, so the domain's (window_start, now] window covers start 00:00
    through end 23:59:59 on the team's calendar. The start stays at local
    midnight across DST: subtracting days from a zone-aware datetime is
    wall-clock arithmetic.
    """

    start: date | None = None
    end: date | None = None

    @property
    def days(self) -> int:
        """Inclusive day count; 0 when the window is open."""
        if self.start is None or self.end is None:
            return 0
        return (self.end - self.start).days + 1

    def resolve(self, tz: tzinfo) -> tuple[datetime | None, int | None]:
        if self.start is None or self.end is None:
            return None, None
        window_end = datetime.combine(self.end + timedelta(days=1), time.min, tzinfo=tz)
        return window_end, self.days


async def get_period(start: date | None = None, end: date | None = None) -> Period:
    if (start is None) != (end is None):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Provide both start and end, or neither",
        )
    if start is None or end is None:
        return Period()
    if end < start:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="end must not be before start",
        )
    period = Period(start=start, end=end)
    if period.days > 365:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Range must not exceed 365 days",
        )
    return period


PeriodDep = Annotated[Period, Depends(get_period)]


def _stats_read(stats: DurationStats | None) -> DurationStatsRead | None:
    if stats is None:
        return None
    return DurationStatsRead(
        p50_seconds=stats.p50.total_seconds(),
        p75_seconds=stats.p75.total_seconds(),
        p85_seconds=stats.p85.total_seconds(),
        p95_seconds=stats.p95.total_seconds(),
        mean_seconds=stats.mean.total_seconds(),
    )


@router.get("", response_model=FlowMetricsRead)
async def get_flow_metrics(
    service: MetricsServiceDep,
    scope: ScopeDep,
    filters: ItemFiltersDep,
    period: PeriodDep,
    window_days: int = Query(default=30, ge=1, le=365),
) -> FlowMetricsRead:
    samples = await service.load_scope(
        team_id=scope.team_id,
        project_id=scope.project_id,
        types=filters.types,
        exclude_states=filters.exclude_states,
    )
    now, period_days = period.resolve(samples.rules.tz)
    metrics = await service.get_flow_metrics(
        scope=samples,
        window_days=period_days or window_days,
        now=now,
    )
    return FlowMetricsRead(
        window_start=metrics.window_start,
        window_end=metrics.window_end,
        completed=metrics.completed,
        wip=metrics.wip,
        lead_time=_stats_read(metrics.lead_time),
        cycle_time=_stats_read(metrics.cycle_time),
        blocked_seconds=metrics.blocked_time.total_seconds(),
        flow_efficiency=metrics.flow_efficiency,
        queue_time=_stats_read(metrics.queue_time),
        touch_time=_stats_read(metrics.touch_time),
    )


@router.get("/history", response_model=FlowHistoryRead)
async def get_flow_history(
    service: MetricsServiceDep,
    scope: ScopeDep,
    filters: ItemFiltersDep,
    period: PeriodDep,
    window_days: int = Query(default=90, ge=7, le=365),
) -> FlowHistoryRead:
    samples = await service.load_scope(
        team_id=scope.team_id,
        project_id=scope.project_id,
        types=filters.types,
        exclude_states=filters.exclude_states,
    )
    now, period_days = period.resolve(samples.rules.tz)
    history = await service.get_flow_history(
        scope=samples,
        window_days=period_days or window_days,
        now=now,
    )
    return FlowHistoryRead.model_validate(history)


@router.get("/lead-time-distribution", response_model=LeadTimeDistributionRead)
async def get_lead_time_distribution(
    service: MetricsServiceDep,
    scope: ScopeDep,
    filters: ItemFiltersDep,
    period: PeriodDep,
    window_days: int = Query(default=90, ge=7, le=365),
) -> LeadTimeDistributionRead:
    samples = await service.load_scope(
        team_id=scope.team_id,
        project_id=scope.project_id,
        types=filters.types,
        exclude_states=filters.exclude_states,
    )
    now, period_days = period.resolve(samples.rules.tz)
    distribution = await service.get_lead_time_distribution(
        scope=samples,
        window_days=period_days or window_days,
        now=now,
    )
    return LeadTimeDistributionRead.model_validate(distribution)


@router.get("/snapshots", response_model=list[MetricSnapshotRead])
async def get_metric_snapshots(
    service: SnapshotServiceDep, scope: ScopeDep
) -> list[MetricSnapshotRead]:
    snapshots = await service.get_metric_history(team_id=scope.team_id, project_id=scope.project_id)
    return [MetricSnapshotRead.model_validate(s) for s in snapshots]


@router.get("/aging-wip", response_model=AgingWipRead)
async def get_aging_wip(
    service: MetricsServiceDep, scope: ScopeDep, filters: ItemFiltersDep
) -> AgingWipRead:
    samples = await service.load_scope(
        team_id=scope.team_id,
        project_id=scope.project_id,
        types=filters.types,
        exclude_states=filters.exclude_states,
    )
    aging = await service.get_aging_wip(scope=samples)
    return AgingWipRead(
        now=aging.now,
        cycle_time_percentile_seconds=(
            aging.cycle_time_percentile.total_seconds()
            if aging.cycle_time_percentile is not None
            else None
        ),
        percentile=aging.percentile,
        items=[
            AgingItemRead(
                work_item_id=item.work_item_id,
                title=item.title,
                state=item.state,
                age_seconds=item.age.total_seconds(),
                over_percentile=item.over_percentile,
            )
            for item in aging.items
        ],
    )


@router.get("/health", response_model=DeliveryHealthRead)
async def get_delivery_health(
    service: MetricsServiceDep,
    scope: ScopeDep,
    filters: ItemFiltersDep,
    period: PeriodDep,
    window_days: int = Query(default=30, ge=7, le=365),
) -> DeliveryHealthRead:
    samples = await service.load_scope(
        team_id=scope.team_id,
        project_id=scope.project_id,
        types=filters.types,
        exclude_states=filters.exclude_states,
    )
    now, period_days = period.resolve(samples.rules.tz)
    health = await service.get_delivery_health(
        scope=samples,
        window_days=period_days or window_days,
        now=now,
    )
    return DeliveryHealthRead.model_validate(health)
