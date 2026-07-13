"""Advisor domain: AI-generated coaching output, grounded in computed metrics.

The AI never calculates — it consumes already-computed metrics and returns
explainable advice. These entities are the platform-neutral shape of that
advice; the LLM adapter lives in Infrastructure.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from app.domain._time import utcnow

PRIORITIES = ("high", "medium", "low")


class Persona(StrEnum):
    """The advisory lens the AI answers through (VISION: AI Personas)."""

    AGILE_COACH = "agile_coach"
    ENGINEERING_ADVISOR = "engineering_advisor"
    PROJECT_ADVISOR = "project_advisor"
    DELIVERY_ANALYST = "delivery_analyst"

    # Meeting personas: values match MeetingType so meeting preps plug into
    # the same feedback/reflect/guidance machinery as the advisory personas.
    DAILY_STANDUP = "daily_standup"
    RETROSPECTIVE = "retrospective"
    PLANNING = "planning"


class MeetingType(StrEnum):
    """A meeting the EM prepares for; each is backed by a learnable Persona."""

    DAILY_STANDUP = "daily_standup"
    RETROSPECTIVE = "retrospective"
    PLANNING = "planning"


def meeting_persona(meeting: MeetingType) -> Persona:
    """The Persona that learns from feedback on this meeting type's preps."""
    return Persona(meeting.value)


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


@dataclass(frozen=True)
class TalkingPoint:
    """One meeting talking point, grounded in quoted metric values."""

    point: str
    detail: str
    evidence: tuple[str, ...] = ()
    needs_decision: bool = False

    def __post_init__(self) -> None:
        if not self.point.strip():
            raise ValueError("point must not be blank")


@dataclass(frozen=True)
class MeetingPrep:
    """Meeting-prep output: a one-line headline + ordered talking points."""

    meeting: MeetingType
    generated_at: datetime
    headline: str
    talking_points: tuple[TalkingPoint, ...]

    def __post_init__(self) -> None:
        if self.generated_at.tzinfo is None:
            raise ValueError("generated_at must be timezone-aware")
        if not self.headline.strip():
            raise ValueError("headline must not be blank")


RATINGS = ("up", "down")


@dataclass(frozen=True)
class AdviceFeedback:
    """One EM verdict on one piece of generated advice — the learning signal."""

    persona: Persona
    rating: str
    advice_summary: str
    comment: str | None = None
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=utcnow)

    def __post_init__(self) -> None:
        if self.rating not in RATINGS:
            raise ValueError(f"rating must be one of {RATINGS}")
        if not self.advice_summary.strip():
            raise ValueError("advice_summary must not be blank")
        if self.created_at.tzinfo is None:
            raise ValueError("created_at must be timezone-aware")


@dataclass(frozen=True)
class PersonaGuidance:
    """One append-only version of a persona's learned-guidance note.

    The highest version is the active one; restoring an old version re-adds
    its text as a new version. No mutable 'active' flag by design.
    """

    persona: Persona
    version: int
    guidance: str
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=utcnow)

    def __post_init__(self) -> None:
        if self.version < 1:
            raise ValueError("version must be >= 1")
        if not self.guidance.strip():
            raise ValueError("guidance must not be blank")
        if self.created_at.tzinfo is None:
            raise ValueError("created_at must be timezone-aware")
