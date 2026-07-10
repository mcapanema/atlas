"""Port for the AI advisor: structured computed metrics in, explainable advice out."""

from dataclasses import dataclass
from typing import Protocol

from app.domain.advisor.entities import DeliveryAdvice
from app.domain.forecasting.monte_carlo import DeliveryForecast
from app.domain.metrics.distribution import LeadTimeDistribution
from app.domain.metrics.summary import FlowMetrics


@dataclass(frozen=True)
class DeliveryContext:
    """Everything the advisor may reason about — all computed, never raw records."""

    flow: FlowMetrics
    distribution: LeadTimeDistribution
    forecast: DeliveryForecast


class AdvisorPort(Protocol):
    """Reasoning adapter (an LLM). Explains metrics; never computes them."""

    async def advise(self, context: DeliveryContext) -> DeliveryAdvice: ...
