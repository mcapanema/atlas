"""Port for the AI advisor: structured computed metrics in, explainable advice out."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from app.domain.advisor.entities import AdviceFeedback, DeliveryAdvice, Persona
from app.domain.forecasting.monte_carlo import DeliveryForecast
from app.domain.metrics.distribution import LeadTimeDistribution
from app.domain.metrics.summary import FlowMetrics


class AdvisorError(Exception):
    """The reasoning adapter failed (API error, malformed or off-schema reply).

    Raised by AdvisorPort implementations; Presentation maps it to 502.
    Deliberately not a ValueError (see DataSourceError in app.domain.sync.port).
    """


@dataclass(frozen=True)
class DeliveryContext:
    """Everything the advisor may reason about — all computed, never raw records."""

    flow: FlowMetrics
    distribution: LeadTimeDistribution
    forecast: DeliveryForecast


class AdvisorPort(Protocol):
    """Reasoning adapter (an LLM). Explains metrics; never computes them.

    `guidance` is the persona's learned note (latest PersonaGuidance version),
    appended to the static system prompt by the adapter.
    """

    async def advise(
        self,
        context: DeliveryContext,
        *,
        persona: Persona = Persona.AGILE_COACH,
        guidance: str | None = None,
    ) -> DeliveryAdvice: ...

    async def reflect(
        self,
        *,
        persona: Persona,
        feedback: Sequence[AdviceFeedback],
        current_guidance: str | None,
    ) -> str:
        """Distill feedback into the persona's next learned-guidance note."""
        ...
