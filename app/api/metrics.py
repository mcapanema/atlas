from dataclasses import dataclass
from typing import Annotated

from fastapi import APIRouter, Depends, Query

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
from app.api.scope import ScopeDep
from app.domain.metrics.summary import DurationStats
from app.domain.work_items.entities import WorkItemType

router = APIRouter(prefix="/api/metrics", tags=["metrics"])


@dataclass(frozen=True)
class ItemFilters:
    """Optional work-item filters shared by every metrics endpoint."""

    types: frozenset[WorkItemType] | None
    exclude_states: frozenset[str] | None


async def get_item_filters(
    types: Annotated[list[WorkItemType] | None, Query()] = None,
    exclude_states: Annotated[list[str] | None, Query()] = None,
) -> ItemFilters:
    return ItemFilters(
        types=frozenset(types) if types else None,
        exclude_states=frozenset(exclude_states) if exclude_states else None,
    )


ItemFiltersDep = Annotated[ItemFilters, Depends(get_item_filters)]


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
    window_days: int = Query(default=30, ge=1, le=365),
) -> FlowMetricsRead:
    samples = await service.load_scope(
        team_id=scope.team_id,
        project_id=scope.project_id,
        types=filters.types,
        exclude_states=filters.exclude_states,
    )
    metrics = await service.get_flow_metrics(scope=samples, window_days=window_days)
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
    window_days: int = Query(default=90, ge=7, le=365),
) -> FlowHistoryRead:
    samples = await service.load_scope(
        team_id=scope.team_id,
        project_id=scope.project_id,
        types=filters.types,
        exclude_states=filters.exclude_states,
    )
    history = await service.get_flow_history(scope=samples, window_days=window_days)
    return FlowHistoryRead.model_validate(history)


@router.get("/lead-time-distribution", response_model=LeadTimeDistributionRead)
async def get_lead_time_distribution(
    service: MetricsServiceDep,
    scope: ScopeDep,
    filters: ItemFiltersDep,
    window_days: int = Query(default=90, ge=7, le=365),
) -> LeadTimeDistributionRead:
    samples = await service.load_scope(
        team_id=scope.team_id,
        project_id=scope.project_id,
        types=filters.types,
        exclude_states=filters.exclude_states,
    )
    distribution = await service.get_lead_time_distribution(
        scope=samples, window_days=window_days
    )
    return LeadTimeDistributionRead.model_validate(distribution)


@router.get("/snapshots", response_model=list[MetricSnapshotRead])
async def get_metric_snapshots(
    service: SnapshotServiceDep, scope: ScopeDep
) -> list[MetricSnapshotRead]:
    snapshots = await service.get_metric_history(
        team_id=scope.team_id, project_id=scope.project_id
    )
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
        cycle_time_p85_seconds=(
            aging.cycle_time_p85.total_seconds() if aging.cycle_time_p85 is not None else None
        ),
        items=[
            AgingItemRead(
                work_item_id=item.work_item_id,
                title=item.title,
                state=item.state,
                age_seconds=item.age.total_seconds(),
                over_p85=item.over_p85,
            )
            for item in aging.items
        ],
    )


@router.get("/health", response_model=DeliveryHealthRead)
async def get_delivery_health(
    service: MetricsServiceDep,
    scope: ScopeDep,
    filters: ItemFiltersDep,
    window_days: int = Query(default=30, ge=7, le=365),
) -> DeliveryHealthRead:
    samples = await service.load_scope(
        team_id=scope.team_id,
        project_id=scope.project_id,
        types=filters.types,
        exclude_states=filters.exclude_states,
    )
    health = await service.get_delivery_health(scope=samples, window_days=window_days)
    return DeliveryHealthRead.model_validate(health)
