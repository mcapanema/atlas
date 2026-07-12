"""Flow history: the time series behind the dashboard charts.

Computed on read from event streams, like summary.py — nothing persisted.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from app.domain.events.entities import Event
from app.domain.metrics.cfd import DailyFlowCount, daily_flow_counts
from app.domain.metrics.samples import derive_flow_sample
from app.domain.metrics.throughput import ThroughputBucket, weekly_throughput


@dataclass(frozen=True)
class FlowHistory:
    """Daily phase counts + weekly throughput over a trailing window."""

    window_start: datetime
    window_end: datetime
    days: tuple[DailyFlowCount, ...]
    weeks: tuple[ThroughputBucket, ...]


def compute_flow_history(
    event_streams: list[list[Event]], *, now: datetime, window_days: int = 90
) -> FlowHistory:
    """Compute chart series for the window (now - window_days, now]."""
    window_start = now - timedelta(days=window_days)
    samples = [
        sample
        for stream in event_streams
        if (sample := derive_flow_sample(stream)) is not None
    ]
    return FlowHistory(
        window_start=window_start,
        window_end=now,
        days=tuple(daily_flow_counts(event_streams, start=window_start, end=now)),
        weeks=tuple(weekly_throughput(samples, end=now, weeks=max(1, window_days // 7))),
    )
