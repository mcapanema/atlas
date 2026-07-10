"""Throughput: completed work items per time window."""

from dataclasses import dataclass
from datetime import datetime, timedelta

from app.domain.metrics.samples import FlowSample


def throughput(samples: list[FlowSample], *, start: datetime, end: datetime) -> int:
    """Count samples completed inside (start, end] — exclusive start, inclusive end."""
    return sum(
        1 for s in samples if s.completed_at is not None and start < s.completed_at <= end
    )


@dataclass(frozen=True)
class ThroughputBucket:
    """Completions in one trailing bucket — start exclusive, end inclusive."""

    start: datetime
    end: datetime
    completed: int


def weekly_throughput(
    samples: list[FlowSample], *, end: datetime, weeks: int
) -> list[ThroughputBucket]:
    """Trailing 7-day buckets ending at `end`, oldest first."""
    buckets: list[ThroughputBucket] = []
    for i in range(weeks, 0, -1):
        bucket_end = end - timedelta(days=7 * (i - 1))
        bucket_start = bucket_end - timedelta(days=7)
        buckets.append(
            ThroughputBucket(
                start=bucket_start,
                end=bucket_end,
                completed=throughput(samples, start=bucket_start, end=bucket_end),
            )
        )
    return buckets
