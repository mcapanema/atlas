from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from app.domain.events.entities import Event
from app.domain.events.repository import EventRepository
from app.domain.forecasting.monte_carlo import (
    CompletionForecast,
    DeliveryForecast,
    daily_throughput_samples,
    delivery_confidence,
    simulate_days_to_complete,
    summarize_completion,
)
from app.domain.metrics.samples import derive_flow_sample
from app.domain.work_items.repository import WorkItemRepository


class ForecastService:
    """Application use cases for Monte Carlo delivery forecasting."""

    def __init__(self, work_items: WorkItemRepository, events: EventRepository) -> None:
        self._work_items = work_items
        self._events = events

    async def get_forecast(
        self,
        *,
        team_id: UUID | None = None,
        project_id: UUID | None = None,
        window_days: int = 90,
        remaining: int | None = None,
        target_date: date | None = None,
        now: datetime | None = None,
    ) -> DeliveryForecast:
        """Forecast completion of the scope's open work from its trailing throughput.

        `remaining` defaults to the scope's not-yet-completed item count
        (items with no events count as open backlog). Deterministic: the
        simulation runs with a fixed seed.
        """
        window_end = now if now is not None else datetime.now(UTC)
        items = await self._work_items.list(team_id=team_id, project_id=project_id)
        events = await self._events.list_for_work_items([item.id for item in items])
        by_item: defaultdict[UUID, list[Event]] = defaultdict(list)
        for event in events:
            by_item[event.work_item_id].append(event)
        samples = [
            sample
            for item in items
            if (sample := derive_flow_sample(by_item[item.id])) is not None
        ]

        completed = sum(1 for s in samples if s.completed_at is not None)
        scope_remaining = remaining if remaining is not None else len(items) - completed

        daily = daily_throughput_samples(samples, end=window_end, days=window_days)
        trial_days = simulate_days_to_complete(daily, remaining=scope_remaining)
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
