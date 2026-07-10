from uuid import UUID

from fastapi import APIRouter, Query

from app.api.deps import MetricsServiceDep
from app.api.schemas import DurationStatsRead, TeamFlowMetricsRead
from app.domain.metrics.summary import DurationStats

router = APIRouter(prefix="/api/metrics", tags=["metrics"])


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


@router.get("", response_model=TeamFlowMetricsRead)
async def get_team_flow_metrics(
    service: MetricsServiceDep,
    team_id: UUID,
    window_days: int = Query(default=30, ge=1, le=365),
) -> TeamFlowMetricsRead:
    metrics = await service.get_team_flow_metrics(team_id, window_days=window_days)
    return TeamFlowMetricsRead(
        window_start=metrics.window_start,
        window_end=metrics.window_end,
        completed=metrics.completed,
        wip=metrics.wip,
        lead_time=_stats_read(metrics.lead_time),
        cycle_time=_stats_read(metrics.cycle_time),
        blocked_seconds=metrics.blocked_time.total_seconds(),
        flow_efficiency=metrics.flow_efficiency,
    )
