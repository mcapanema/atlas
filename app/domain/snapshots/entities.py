"""Persisted point-in-time aggregations of the computed analytics.

The SPEC's Snapshot concept: an immutable historical aggregation of
metrics. One row per scope (team XOR project) per UTC day, captured after
sync — metric snapshots feed dashboard history, forecast snapshots feed
forecast-accuracy calibration.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from uuid import UUID, uuid4

from app.domain._time import utcnow


def _require_one_scope(team_id: UUID | None, project_id: UUID | None) -> None:
    if (team_id is None) == (project_id is None):
        raise ValueError("Exactly one of team_id or project_id must be set")


@dataclass(frozen=True)
class MetricSnapshot:
    """One scope's flow metrics captured on one UTC day."""

    captured_on: date
    window_days: int
    completed: int
    wip: int
    lead_time_p50_seconds: float | None
    lead_time_p85_seconds: float | None
    cycle_time_p50_seconds: float | None
    cycle_time_p85_seconds: float | None
    blocked_seconds: float
    flow_efficiency: float | None
    team_id: UUID | None = None
    project_id: UUID | None = None
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=utcnow)

    def __post_init__(self) -> None:
        _require_one_scope(self.team_id, self.project_id)


@dataclass(frozen=True)
class ForecastSnapshot:
    """One scope's Monte Carlo forecast captured on one UTC day.

    p50_days/p85_days are None when the scope had no throughput history to
    simulate from (nothing was predicted).
    """

    captured_on: date
    window_days: int
    remaining: int
    p50_days: int | None
    p85_days: int | None
    team_id: UUID | None = None
    project_id: UUID | None = None
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=utcnow)

    def __post_init__(self) -> None:
        _require_one_scope(self.team_id, self.project_id)
