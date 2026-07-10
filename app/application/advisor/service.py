from datetime import UTC, datetime
from uuid import UUID

from app.application.forecasting.service import ForecastService
from app.application.metrics.service import MetricsService
from app.domain.advisor.entities import DeliveryAdvice
from app.domain.advisor.port import AdvisorPort, DeliveryContext


class AdvisorService:
    """Application use case: assemble computed metrics, ask the advisor to explain them.

    Composes MetricsService and ForecastService (Application-layer reuse of the
    metric derivations) — the AI itself never computes anything.
    """

    def __init__(
        self, metrics: MetricsService, forecasts: ForecastService, advisor: AdvisorPort
    ) -> None:
        self._metrics = metrics
        self._forecasts = forecasts
        self._advisor = advisor

    async def get_advice(
        self,
        *,
        team_id: UUID | None = None,
        project_id: UUID | None = None,
        window_days: int = 30,
        now: datetime | None = None,
    ) -> DeliveryAdvice:
        """Generate coaching advice for the scope's current delivery picture.

        `window_days` scopes the flow summary; the lead-time distribution and
        forecast keep their 90-day defaults, matching the dashboards.
        """
        window_end = now if now is not None else datetime.now(UTC)
        flow = await self._metrics.get_flow_metrics(
            team_id=team_id, project_id=project_id, window_days=window_days, now=window_end
        )
        distribution = await self._metrics.get_lead_time_distribution(
            team_id=team_id, project_id=project_id, now=window_end
        )
        forecast = await self._forecasts.get_forecast(
            team_id=team_id, project_id=project_id, now=window_end
        )
        return await self._advisor.advise(
            DeliveryContext(flow=flow, distribution=distribution, forecast=forecast)
        )
