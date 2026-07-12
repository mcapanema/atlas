"""Advisor domain: AI-generated coaching output, grounded in computed metrics.

The AI never calculates — it consumes already-computed metrics and returns
explainable advice. These entities are the platform-neutral shape of that
advice; the LLM adapter lives in Infrastructure.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

PRIORITIES = ("high", "medium", "low")


class Persona(StrEnum):
    """The advisory lens the AI answers through (VISION: AI Personas)."""

    AGILE_COACH = "agile_coach"
    ENGINEERING_ADVISOR = "engineering_advisor"
    PROJECT_ADVISOR = "project_advisor"
    DELIVERY_ANALYST = "delivery_analyst"


@dataclass(frozen=True)
class Recommendation:
    """One actionable improvement with its root cause and supporting evidence."""

    title: str
    priority: str
    problem: str
    root_cause: str
    action: str
    evidence: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.title.strip():
            raise ValueError("title must not be blank")
        if self.priority not in PRIORITIES:
            raise ValueError(f"priority must be one of {PRIORITIES}")


@dataclass(frozen=True)
class DeliveryAdvice:
    """Coaching output for a scope: narrative summary + prioritized recommendations."""

    generated_at: datetime
    summary: str
    recommendations: tuple[Recommendation, ...]

    def __post_init__(self) -> None:
        if self.generated_at.tzinfo is None:
            raise ValueError("generated_at must be timezone-aware")
        if not self.summary.strip():
            raise ValueError("summary must not be blank")
