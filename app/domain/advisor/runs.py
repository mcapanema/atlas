"""AdviceRun: one advice / meeting-prep generation, with status and result."""

from dataclasses import dataclass, field, replace
from datetime import date, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from app.domain._time import utcnow
from app.domain.advisor.entities import (
    DeliveryAdvice,
    MeetingPrep,
    MeetingType,
    Persona,
    meeting_persona,
)


class RunStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


def run_params(**values: int | date | None) -> str:
    """Canonical key for a run's request parameters: sorted `name=value` pairs.

    `None` values are omitted; dates use ISO format.
    """
    parts = []
    for name in sorted(values):
        value = values[name]
        if value is None:
            continue
        text = value.isoformat() if isinstance(value, date) else str(value)
        parts.append(f"{name}={text}")
    return "&".join(parts)


@dataclass(frozen=True)
class AdviceRun:
    """One generation request for a team or project scope, and its outcome."""

    persona: Persona
    params: str
    team_id: UUID | None = None
    project_id: UUID | None = None
    status: RunStatus = RunStatus.RUNNING
    result: DeliveryAdvice | MeetingPrep | None = None
    error: str | None = None
    id: UUID = field(default_factory=uuid4)
    requested_at: datetime = field(default_factory=utcnow)
    finished_at: datetime | None = None

    def __post_init__(self) -> None:
        if (self.team_id is None) == (self.project_id is None):
            raise ValueError("exactly one of team_id or project_id is required")
        if self.requested_at.tzinfo is None:
            raise ValueError("requested_at must be timezone-aware")
        if self.finished_at is not None and self.finished_at.tzinfo is None:
            raise ValueError("finished_at must be timezone-aware")
        self._check_status()
        self._check_result_kind()

    def _check_status(self) -> None:
        if self.status is RunStatus.SUCCEEDED:
            if self.result is None or self.finished_at is None:
                raise ValueError("a succeeded run needs a result and finished_at")
            if self.error is not None:
                raise ValueError("a succeeded run has no error")
        elif self.status is RunStatus.FAILED:
            if self.error is None or not self.error.strip():
                raise ValueError("a failed run needs a non-blank error")
            if self.finished_at is None or self.result is not None:
                raise ValueError("a failed run needs finished_at and no result")
        elif self.result is not None or self.error is not None or self.finished_at is not None:
            raise ValueError("a running run has no result, error or finished_at")

    def _check_result_kind(self) -> None:
        if isinstance(self.result, MeetingPrep):
            if meeting_persona(self.result.meeting) != self.persona:
                raise ValueError("a meeting prep needs its meeting persona")
        elif self.result is not None and self.persona in {meeting_persona(m) for m in MeetingType}:
            raise ValueError("advice needs a non-meeting persona")

    def succeed(self, result: DeliveryAdvice | MeetingPrep, *, at: datetime) -> "AdviceRun":
        return replace(self, status=RunStatus.SUCCEEDED, result=result, finished_at=at)

    def fail(self, error: str, *, at: datetime) -> "AdviceRun":
        return replace(self, status=RunStatus.FAILED, error=error, finished_at=at)
