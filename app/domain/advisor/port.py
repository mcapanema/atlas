"""Port for the AI advisor: structured computed metrics in, explainable advice out."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from app.domain.advisor.entities import (
    AdviceFeedback,
    DeliveryAdvice,
    MeetingPrep,
    MeetingType,
    Persona,
)
from app.domain.forecasting.monte_carlo import DeliveryForecast
from app.domain.metrics.aging import AgingWip
from app.domain.metrics.distribution import LeadTimeDistribution
from app.domain.metrics.health import DeliveryHealth
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


@dataclass(frozen=True)
class MeetingContext:
    """Everything meeting prep may reason about — the advisor's delivery
    context plus the health and aging views the MCP meeting_brief exposes."""

    delivery: DeliveryContext
    health: DeliveryHealth
    aging: AgingWip


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

    async def prepare_meeting(
        self,
        context: MeetingContext,
        *,
        meeting: MeetingType,
        guidance: str | None = None,
    ) -> MeetingPrep:
        """Turn the meeting digest into a headline + talking points.

        `guidance` is the meeting persona's learned note, same contract
        as advise().
        """
        ...

    async def reflect(
        self,
        *,
        persona: Persona,
        feedback: Sequence[AdviceFeedback],
        current_guidance: str | None,
    ) -> str:
        """Distill feedback into the persona's next learned-guidance note."""
        ...
