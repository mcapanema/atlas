import asyncio
from collections.abc import Set as AbstractSet
from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from app.application.metric_rules.resolver import MetricRulesResolver
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
from app.domain.metrics.samples import observed_history_days
from app.domain.work_items.entities import WorkItemType
from app.domain.work_items.repository import WorkItemRepository


class ForecastService:
    """Application use cases for Monte Carlo delivery forecasting."""

    def __init__(
        self,
        work_items: WorkItemRepository,
        events: EventRepository,
        rules: MetricRulesResolver | None = None,
    ) -> None:
        self._scope = ScopeSampleLoader(work_items, events, rules)

    async def load_scope(
        self,
        *,
        team_id: UUID | None = None,
        project_id: UUID | None = None,
        types: AbstractSet[WorkItemType] | None = None,
        exclude_states: AbstractSet[str] | None = None,
    ) -> ScopeSamples:
        """One filtered scope load, handed to `get_forecast` via `scope=`."""
        return await self._scope.load(
            team_id=team_id,
            project_id=project_id,
            types=types,
            exclude_states=exclude_states,
        )

    async def get_forecast(
        self,
        *,
        team_id: UUID | None = None,
        project_id: UUID | None = None,
        window_days: int | None = None,
        remaining: int | None = None,
        target_date: date | None = None,
        now: datetime | None = None,
        scope: ScopeSamples | None = None,
    ) -> DeliveryForecast:
        """Forecast completion of the scope's open work from its trailing throughput.

        `remaining` defaults to the scope's open items in a state type its
        remaining_state_types rule counts (eventless backlog included). Deterministic:
        the simulation runs with a fixed seed. `window_days` defaults to the scope
        team's forecast_history_days rule.
        """
        window_end = now if now is not None else datetime.now(UTC)
        if scope is None:
            scope = await self._scope.load(team_id=team_id, project_id=project_id)

        history_window = (
            window_days if window_days is not None else scope.rules.forecast_history_days
        )

        scope_remaining = remaining if remaining is not None else _open_count(scope)

        history_days = observed_history_days(scope.samples, end=window_end, days=history_window)
        daily = daily_throughput_samples(scope.samples, end=window_end, days=history_days)
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
                # Days on the team's calendar: a UTC date is a day ahead of
                # São Paulo from 21:00 local.
                today = window_end.astimezone(scope.rules.tz).date()
                confidence = delivery_confidence(trial_days, within_days=(target_date - today).days)
        completions = [s.completed_at for s in scope.samples if s.completed_at is not None]
        last_completed_at = max((at for at in completions if at <= window_end), default=None)
        return DeliveryForecast(
            window_start=window_end - timedelta(days=history_days),
            window_end=window_end,
            remaining=scope_remaining,
            completion=completion,
            confidence=confidence,
            last_completed_at=last_completed_at,
        )


def _open_count(scope: ScopeSamples) -> int:
    """Remaining work: the loader's state-type-aware count; all open items if hand-built."""
    if scope.remaining_count is not None:
        return scope.remaining_count
    closed = sum(1 for s in scope.samples if s.completed_at is not None or s.canceled)
    return scope.item_count - closed
