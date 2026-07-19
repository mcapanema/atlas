"""Flow history: the time series behind the dashboard charts.

Computed on read from event streams, like summary.py — nothing persisted.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from app.domain.events.entities import Event
from app.domain.metrics.cfd import DailyFlowCount, daily_flow_counts
from app.domain.metrics.samples import derive_flow_sample
from app.domain.metrics.throughput import ThroughputBucket, bucketed_throughput


@dataclass(frozen=True)
class FlowHistory:
    """Daily phase counts + throughput buckets over a trailing window."""

    window_start: datetime
    window_end: datetime
    days: tuple[DailyFlowCount, ...]
    buckets: tuple[ThroughputBucket, ...]
    bucket_days: int
    data_as_of: datetime | None


# Short windows have no weekly shape to read — a 7-day window is one weekly
# bar, which just restates the Throughput stat tile. Bucket those per day.
DAILY_BUCKET_MAX_DAYS = 21


def _bucketing(window_days: int) -> tuple[int, int]:
    """(count, bucket_days) for the window — daily when short, weekly when long."""
    if window_days <= DAILY_BUCKET_MAX_DAYS:
        return window_days, 1
    return window_days // 7, 7


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
    # The freshest thing we know about this scope. Events are append-only and
    # recorded_at is stamped on ingest, so the newest one dates the last sync
    # that touched this scope — no sync-log table needed.
    recorded = [event.recorded_at for stream in event_streams for event in stream]
    count, bucket_days = _bucketing(window_days)
    return FlowHistory(
        window_start=window_start,
        window_end=now,
        days=tuple(daily_flow_counts(event_streams, start=window_start, end=now)),
        buckets=tuple(
            bucketed_throughput(samples, end=now, count=count, bucket_days=bucket_days)
        ),
        bucket_days=bucket_days,
        data_as_of=max(recorded, default=None),
    )
