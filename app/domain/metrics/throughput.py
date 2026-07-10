"""Throughput: completed work items per time window."""

from datetime import datetime

from app.domain.metrics.samples import FlowSample


def throughput(samples: list[FlowSample], *, start: datetime, end: datetime) -> int:
    """Count samples completed inside (start, end] — exclusive start, inclusive end."""
    return sum(
        1 for s in samples if s.completed_at is not None and start < s.completed_at <= end
    )
