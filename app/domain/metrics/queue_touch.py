"""Queue Time and Touch Time: waiting vs actively-worked share of delivery.

Queue time = pre-start wait (created -> started) plus blocked time.
Touch time = cycle time minus blocked time, floored at zero.
Completed-and-started samples only.

ponytail: BLOCKED periods and pre-start wait are the only queue signals
today — count per-state queue waits (e.g. idle time in Review) once
workflow states carry a category the domain can tell apart (same ceiling
as flow_efficiency).
"""

from datetime import timedelta

from app.domain.metrics.samples import FlowSample


def queue_times(samples: list[FlowSample]) -> list[timedelta]:
    """Queue time per sample that was both started and completed."""
    return [
        (s.started_at - s.created_at) + s.blocked_time
        for s in samples
        if s.completed_at is not None and s.started_at is not None
    ]


def touch_times(samples: list[FlowSample]) -> list[timedelta]:
    """Active-work time per sample that was both started and completed."""
    result: list[timedelta] = []
    for s in samples:
        if s.completed_at is None or s.started_at is None:
            continue
        cycle = s.completed_at - s.started_at
        result.append(cycle - min(s.blocked_time, cycle))
    return result
