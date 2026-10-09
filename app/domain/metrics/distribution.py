"""Lead Time Distribution: day-binned histogram of completed lead times."""

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.domain.metrics.lead_time import lead_times
from app.domain.metrics.samples import FlowSample
from app.domain.metrics.stats import percentile
from app.domain.metrics.windows import CHART_WINDOW_DAYS


@dataclass(frozen=True)
class DurationBin:
    """Count of durations d with start_days <= d < end_days."""

    start_days: int
    end_days: int
    count: int


@dataclass(frozen=True)
class LeadTimeDistribution:
    """Histogram of lead times for items completed in the trailing window.

    p50/p85 are the window's exact lead-time percentiles (the stat tiles'
    method), so the chart's reference lines needn't approximate from bins.
    """

    window_start: datetime
    window_end: datetime
    bins: tuple[DurationBin, ...]
    p50_seconds: float | None = None
    p85_seconds: float | None = None


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
    samples: list[FlowSample], *, now: datetime, window_days: int = CHART_WINDOW_DAYS
) -> LeadTimeDistribution:
    """Histogram of lead times of samples completed in (now - window_days, now]."""
    window_start = now - timedelta(days=window_days)
    in_window = [
        s for s in samples if s.completed_at is not None and window_start < s.completed_at <= now
    ]
    durations = lead_times(in_window)
    seconds = [d.total_seconds() for d in durations]
    return LeadTimeDistribution(
        window_start=window_start,
        window_end=now,
        bins=tuple(duration_bins(durations)),
        p50_seconds=percentile(seconds, 50) if seconds else None,
        p85_seconds=percentile(seconds, 85) if seconds else None,
    )
