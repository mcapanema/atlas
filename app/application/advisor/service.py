from datetime import UTC, datetime
from uuid import UUID

from app.application.forecasting.service import ForecastService
from app.application.metrics.service import MetricsService
from app.domain.advisor.port import DeliveryContext


class AdvisorService:
    """Application use case: assemble the computed-metrics context for the advisor.

    Composes MetricsService and ForecastService (Application-layer reuse of the
    metric derivations) — the AI itself never computes anything. The port call
    happens in Presentation so the DB transaction can be released before the
    (up to 120s) LLM request; an open SQLite transaction there blocks every
    other writer for the duration.
    """

    def __init__(self, metrics: MetricsService, forecasts: ForecastService) -> None:
        self._metrics = metrics
        self._forecasts = forecasts

    async def build_context(
        self,
        *,
        team_id: UUID | None = None,
        project_id: UUID | None = None,
        window_days: int = 30,
        now: datetime | None = None,
    ) -> DeliveryContext:
        """Assemble the scope's current delivery picture for the advisor.

        `window_days` scopes the flow summary; the lead-time distribution and
        forecast keep their 90-day defaults, matching the dashboards. The
        scope's items and events are loaded once and shared by all three
        computations.
        """
        window_end = now if now is not None else datetime.now(UTC)
        scope = await self._metrics.load_scope(team_id=team_id, project_id=project_id)
        flow = await self._metrics.get_flow_metrics(
            window_days=window_days, now=window_end, scope=scope
        )
        distribution = await self._metrics.get_lead_time_distribution(
            now=window_end, scope=scope
        )
        forecast = await self._forecasts.get_forecast(now=window_end, scope=scope)
        return DeliveryContext(flow=flow, distribution=distribution, forecast=forecast)
