"""Lead Time Distribution: day-binned histogram of completed lead times."""

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.domain.metrics.lead_time import lead_times
from app.domain.metrics.samples import FlowSample


@dataclass(frozen=True)
class DurationBin:
    """Count of durations d with start_days <= d < end_days."""

    start_days: int
    end_days: int
    count: int


@dataclass(frozen=True)
class LeadTimeDistribution:
    """Histogram of lead times for items completed in the trailing window."""

    window_start: datetime
    window_end: datetime
    bins: tuple[DurationBin, ...]


def duration_bins(durations: list[timedelta]) -> list[DurationBin]:
    """1-day-wide bins from day 0 through the longest duration; [] when empty.

    Empty bins between occupied ones are included so the histogram chart
    shows real gaps instead of silently compressing the x axis.
    """
    if not durations:
        return []
    days = [d // timedelta(days=1) for d in durations]
    counts = Counter(days)
    return [
        DurationBin(start_days=day, end_days=day + 1, count=counts.get(day, 0))
        for day in range(max(days) + 1)
    ]


def compute_lead_time_distribution(
    samples: list[FlowSample], *, now: datetime, window_days: int = 90
) -> LeadTimeDistribution:
    """Histogram of lead times of samples completed in (now - window_days, now]."""
    window_start = now - timedelta(days=window_days)
    in_window = [
        s for s in samples if s.completed_at is not None and window_start < s.completed_at <= now
    ]
    return LeadTimeDistribution(
        window_start=window_start,
        window_end=now,
        bins=tuple(duration_bins(lead_times(in_window))),
    )
