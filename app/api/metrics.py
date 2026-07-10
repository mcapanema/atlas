from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import MetricsServiceDep
from app.api.schemas import (
    DailyFlowCountRead,
    DurationBinRead,
    DurationStatsRead,
    FlowHistoryRead,
    FlowMetricsRead,
    LeadTimeDistributionRead,
    ThroughputBucketRead,
)
from app.domain.metrics.summary import DurationStats

router = APIRouter(prefix="/api/metrics", tags=["metrics"])


def _require_exactly_one_scope(team_id: UUID | None, project_id: UUID | None) -> None:
    if (team_id is None) == (project_id is None):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Provide exactly one of team_id or project_id",
        )


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
    team_id: UUID | None = None,
    project_id: UUID | None = None,
    window_days: int = Query(default=30, ge=1, le=365),
) -> FlowMetricsRead:
    _require_exactly_one_scope(team_id, project_id)
    metrics = await service.get_flow_metrics(
        team_id=team_id, project_id=project_id, window_days=window_days
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
    )


@router.get("/history", response_model=FlowHistoryRead)
async def get_flow_history(
    service: MetricsServiceDep,
    team_id: UUID | None = None,
    project_id: UUID | None = None,
    window_days: int = Query(default=90, ge=7, le=365),
) -> FlowHistoryRead:
    _require_exactly_one_scope(team_id, project_id)
    history = await service.get_flow_history(
        team_id=team_id, project_id=project_id, window_days=window_days
    )
    return FlowHistoryRead(
        window_start=history.window_start,
        window_end=history.window_end,
        days=[
            DailyFlowCountRead(
                day=d.day, todo=d.todo, in_progress=d.in_progress, done=d.done
            )
            for d in history.days
        ],
        weeks=[
            ThroughputBucketRead(start=w.start, end=w.end, completed=w.completed)
            for w in history.weeks
        ],
    )


@router.get("/lead-time-distribution", response_model=LeadTimeDistributionRead)
async def get_lead_time_distribution(
    service: MetricsServiceDep,
    team_id: UUID | None = None,
    project_id: UUID | None = None,
    window_days: int = Query(default=90, ge=7, le=365),
) -> LeadTimeDistributionRead:
    _require_exactly_one_scope(team_id, project_id)
    distribution = await service.get_lead_time_distribution(
        team_id=team_id, project_id=project_id, window_days=window_days
    )
    return LeadTimeDistributionRead(
        window_start=distribution.window_start,
        window_end=distribution.window_end,
        bins=[
            DurationBinRead(start_days=b.start_days, end_days=b.end_days, count=b.count)
            for b in distribution.bins
        ],
    )
