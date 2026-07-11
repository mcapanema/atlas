import asyncio
from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from app.application.scope import ScopeSampleLoader, ScopeSamples
from app.domain.events.repository import EventRepository
from app.domain.forecasting.monte_carlo import (
    CompletionForecast,
    DeliveryForecast,
    daily_throughput_samples,
    delivery_confidence,
    simulate_days_to_complete,
    summarize_completion,
)
from app.domain.work_items.repository import WorkItemRepository


class ForecastService:
    """Application use cases for Monte Carlo delivery forecasting."""

    def __init__(self, work_items: WorkItemRepository, events: EventRepository) -> None:
        self._scope = ScopeSampleLoader(work_items, events)

    async def get_forecast(
        self,
        *,
        team_id: UUID | None = None,
        project_id: UUID | None = None,
        window_days: int = 90,
        remaining: int | None = None,
        target_date: date | None = None,
        now: datetime | None = None,
        scope: ScopeSamples | None = None,
    ) -> DeliveryForecast:
        """Forecast completion of the scope's open work from its trailing throughput.

        `remaining` defaults to the scope's not-yet-completed item count
        (items with no events count as open backlog). Deterministic: the
        simulation runs with a fixed seed.
        """
        window_end = now if now is not None else datetime.now(UTC)
        if scope is None:
            scope = await self._scope.load(team_id=team_id, project_id=project_id)

        completed = sum(1 for s in scope.samples if s.completed_at is not None)
        scope_remaining = (
            remaining if remaining is not None else scope.item_count - completed
        )

        daily = daily_throughput_samples(scope.samples, end=window_end, days=window_days)
        # ponytail: the 2k-trial simulation is pure CPU (~0.9s worst case) —
        # run it in a worker thread so the event loop (incl. /health) stays
        # responsive. Cache or precompute forecasts if it ever needs more.
        trial_days = await asyncio.to_thread(
            simulate_days_to_complete, daily, remaining=scope_remaining
        )
        completion: CompletionForecast | None = None
        confidence: float | None = None
        if trial_days is not None:
            completion = summarize_completion(trial_days, remaining=scope_remaining)
            if target_date is not None:
                within = (target_date - window_end.date()).days
                confidence = delivery_confidence(trial_days, within_days=within)
        return DeliveryForecast(
            window_start=window_end - timedelta(days=window_days),
            window_end=window_end,
            remaining=scope_remaining,
            completion=completion,
            confidence=confidence,
        )
