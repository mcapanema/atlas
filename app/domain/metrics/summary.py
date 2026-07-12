"""Aggregate a scope's FlowSamples into one FlowMetrics snapshot.

Computed on read — nothing here is persisted. Window semantics: duration
percentiles, blocked time, and flow efficiency cover items completed in the
trailing window; WIP is the instant `now`.
"""

import statistics
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.domain.metrics.blocked_time import total_blocked_time
from app.domain.metrics.cycle_time import cycle_times
from app.domain.metrics.flow_efficiency import flow_efficiency
from app.domain.metrics.lead_time import lead_times
from app.domain.metrics.queue_touch import queue_times, touch_times
from app.domain.metrics.samples import FlowSample
from app.domain.metrics.stats import percentile
from app.domain.metrics.throughput import throughput
from app.domain.metrics.wip import wip


@dataclass(frozen=True)
class DurationStats:
    """Distribution summary of a set of durations."""

    p50: timedelta
    p75: timedelta
    p85: timedelta
    p95: timedelta
    mean: timedelta


@dataclass(frozen=True)
class FlowMetrics:
    """Flow metrics for a scope (team or project) over a trailing window ending at window_end."""

    window_start: datetime
    window_end: datetime
    completed: int
    wip: int
    lead_time: DurationStats | None
    cycle_time: DurationStats | None
    blocked_time: timedelta
    flow_efficiency: float | None
    queue_time: DurationStats | None = None
    touch_time: DurationStats | None = None


def _duration_stats(durations: list[timedelta]) -> DurationStats | None:
    if not durations:
        return None
    seconds = [d.total_seconds() for d in durations]
    return DurationStats(
        p50=timedelta(seconds=percentile(seconds, 50)),
        p75=timedelta(seconds=percentile(seconds, 75)),
        p85=timedelta(seconds=percentile(seconds, 85)),
        p95=timedelta(seconds=percentile(seconds, 95)),
        mean=timedelta(seconds=statistics.fmean(seconds)),
    )


def compute_flow_metrics(
    samples: list[FlowSample], *, now: datetime, window_days: int = 30
) -> FlowMetrics:
    """Aggregate samples into FlowMetrics for the window (now - window_days, now]."""
    window_start = now - timedelta(days=window_days)
    in_window = [
        s for s in samples if s.completed_at is not None and window_start < s.completed_at <= now
    ]
    return FlowMetrics(
        window_start=window_start,
        window_end=now,
        completed=throughput(samples, start=window_start, end=now),
        wip=wip(samples, at=now),
        lead_time=_duration_stats(lead_times(in_window)),
        cycle_time=_duration_stats(cycle_times(in_window)),
        blocked_time=total_blocked_time(in_window),
        flow_efficiency=flow_efficiency(in_window),
        queue_time=_duration_stats(queue_times(in_window)),
        touch_time=_duration_stats(touch_times(in_window)),
    )
