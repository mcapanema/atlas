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


def bucketed_throughput(
    samples: list[FlowSample], *, end: datetime, count: int, bucket_days: int
) -> list[ThroughputBucket]:
    """`count` trailing buckets of `bucket_days` each, ending at `end`, oldest first."""
    size = timedelta(days=bucket_days)
    buckets: list[ThroughputBucket] = []
    for i in range(count, 0, -1):
        bucket_end = end - size * (i - 1)
        bucket_start = bucket_end - size
        buckets.append(
            ThroughputBucket(
                start=bucket_start,
                end=bucket_end,
                completed=throughput(samples, start=bucket_start, end=bucket_end),
            )
        )
    return buckets
