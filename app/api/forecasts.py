from datetime import date, datetime, timedelta

from fastapi import APIRouter, Query

from app.api.deps import ForecastServiceDep
from app.api.schemas import CompletionForecastRead, ForecastRead, OutcomeBucketRead
from app.api.scope import ScopeDep
from app.domain.forecasting.monte_carlo import CompletionForecast

router = APIRouter(prefix="/api/forecasts", tags=["forecasts"])


def _completion_read(
    completion: CompletionForecast | None, origin: datetime
) -> CompletionForecastRead | None:
    if completion is None:
        return None
    return CompletionForecastRead(
        trials=completion.trials,
        p50_date=origin + timedelta(days=completion.p50_days),
        p75_date=origin + timedelta(days=completion.p75_days),
        p85_date=origin + timedelta(days=completion.p85_days),
        p95_date=origin + timedelta(days=completion.p95_days),
        outcomes=[
            OutcomeBucketRead(days=o.days, trials=o.trials) for o in completion.outcomes
        ],
    )


@router.get("", response_model=ForecastRead)
async def get_forecast(
    service: ForecastServiceDep,
    scope: ScopeDep,
    window_days: int = Query(default=90, ge=7, le=365),
    remaining: int | None = Query(default=None, ge=0),
    target_date: date | None = None,
) -> ForecastRead:
    forecast = await service.get_forecast(
        team_id=scope.team_id,
        project_id=scope.project_id,
        window_days=window_days,
        remaining=remaining,
        target_date=target_date,
    )
    return ForecastRead(
        window_start=forecast.window_start,
        window_end=forecast.window_end,
        remaining=forecast.remaining,
        completion=_completion_read(forecast.completion, forecast.window_end),
        confidence=forecast.confidence,
    )
