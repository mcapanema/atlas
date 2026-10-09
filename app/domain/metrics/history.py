"""Flow history: the time series behind the dashboard charts.

Computed on read from event streams, like summary.py — nothing persisted.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.domain.events.entities import Event
from app.domain.metric_rules.entities import DEFAULT_RULES, MetricRules
from app.domain.metrics.cfd import DailyFlowCount, daily_flow_counts
from app.domain.metrics.samples import FlowSample, derive_flow_sample
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


def _bucketing(window_days: int, daily_max_days: int) -> tuple[int, int]:
    """(count, bucket_days) for the window — daily up to `daily_max_days`, else weekly.

    Weekly count rounds up so the buckets cover the whole window (the oldest
    is clipped to the window start); flooring dropped up to 6 days of
    completions the Throughput tile still counted.
    """
    if window_days <= daily_max_days:
        return window_days, 1
    return -(-window_days // 7), 7


def compute_flow_history(
    event_streams: list[list[Event]],
    *,
    now: datetime,
    window_days: int = 90,
    samples: Sequence[FlowSample] | None = None,
    stream_rules: Sequence[MetricRules] | None = None,
    rules: MetricRules = DEFAULT_RULES,
    synced_at: datetime | None = None,
) -> FlowHistory:
    """Compute chart series for the window (now - window_days, now].

    `samples` and `stream_rules` are the streams' derived samples and
    per-item rules (aligned by index) when the caller folded them per team;
    omitted, the built-in rules apply. `rules` (the scope's) set the day
    boundaries' timezone and the daily/weekly bucketing cut-over.
    `synced_at` is the scope's team's last sync; it dates the data when that
    sync brought no newer event.
    """
    window_start = now - timedelta(days=window_days)
    derived = (
        list(samples)
        if samples is not None
        else [s for stream in event_streams if (s := derive_flow_sample(stream)) is not None]
    )
    # The freshest thing we know about this scope: the newest ingested event
    # (recorded_at is stamped on ingest) or the team's last sync, whichever
    # is later — a sync that found nothing new still dates the data.
    recorded = [event.recorded_at for stream in event_streams for event in stream]
    if synced_at is not None:
        recorded.append(synced_at)
    count, bucket_days = _bucketing(window_days, rules.daily_bucket_max_days)
    return FlowHistory(
        window_start=window_start,
        window_end=now,
        days=tuple(
            daily_flow_counts(
                event_streams,
                start=window_start,
                end=now,
                tz=rules.tz,
                stream_rules=stream_rules,
            )
        ),
        buckets=tuple(
            bucketed_throughput(
                derived, end=now, count=count, bucket_days=bucket_days, start=window_start
            )
        ),
        bucket_days=bucket_days,
        data_as_of=max(recorded, default=None),
    )
