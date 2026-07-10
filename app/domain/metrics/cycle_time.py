"""Cycle Time: first start -> completion, one duration per completed work item."""

from datetime import timedelta

from app.domain.metrics.samples import FlowSample


def cycle_times(samples: list[FlowSample]) -> list[timedelta]:
    """Cycle time per sample that was both started and completed."""
    return [
        s.completed_at - s.started_at
        for s in samples
        if s.completed_at is not None and s.started_at is not None
    ]
