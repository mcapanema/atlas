"""An organization's automatic-sync schedule (ADR-0014)."""

from dataclasses import dataclass, field
from datetime import datetime, time
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.domain._time import utcnow

# ISO weekdays, as date.isoweekday() numbers them: 1 = Monday … 7 = Sunday.
WEEKDAYS = frozenset(range(1, 8))
MIN_INTERVAL_MINUTES = 15
MAX_INTERVAL_MINUTES = 24 * 60


@dataclass(frozen=True)
class SyncRun:
    """The outcome of one automatic sync."""

    # The scheduled slot this run satisfied; the next run waits for a later one.
    slot_at: datetime
    finished_at: datetime
    # None when the sync succeeded.
    error: str | None = None


@dataclass
class SyncSchedule:
    """When Atlas syncs an organization by itself: weekdays x a local window x an interval."""

    organization_id: UUID
    enabled: bool
    days: frozenset[int]
    # Wall-clock times in `timezone`; the window includes both ends.
    window_start: time
    window_end: time
    interval_minutes: int
    # IANA zone name, e.g. "America/Sao_Paulo".
    timezone: str
    # Last settings change: slots at or before it never fire.
    updated_at: datetime = field(default_factory=utcnow)
    last_run: SyncRun | None = None

    def __post_init__(self) -> None:
        if not self.days <= WEEKDAYS:
            raise ValueError("Days must be ISO weekdays: 1 (Monday) to 7 (Sunday)")
        if self.enabled and not self.days:
            raise ValueError("An enabled auto sync needs at least one day")
        _check_window(self.window_start, self.window_end)
        if not MIN_INTERVAL_MINUTES <= self.interval_minutes <= MAX_INTERVAL_MINUTES:
            raise ValueError(
                f"Interval must be between {MIN_INTERVAL_MINUTES} and "
                f"{MAX_INTERVAL_MINUTES} minutes"
            )
        _check_timezone(self.timezone)
        if self.updated_at.tzinfo is None:
            raise ValueError("updated_at must be timezone-aware")


def _check_window(start: time, end: time) -> None:
    for moment in (start, end):
        if moment.tzinfo is not None or moment.second or moment.microsecond:
            raise ValueError("Window times must be whole minutes of local time, without a zone")
    if start > end:
        raise ValueError("The window must start before it ends; overnight windows aren't supported")


def _check_timezone(name: str) -> None:
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:  # ValueError: "" or a path
        raise ValueError(f"Unknown timezone: {name!r}") from exc
