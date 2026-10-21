"""Queue Time and Touch Time: waiting vs actively-worked share of delivery.

Queue time = pre-start wait (arrival -> started) plus in-cycle wait:
blocked time and time in the team's wait states (FlowSample.wait_time).
Touch time = cycle time minus that wait, floored at zero.
Completed-and-started samples only. Wait states are the same manual
per-team list as flow efficiency's (see flow_efficiency.py).
"""

from datetime import timedelta

from app.domain.metrics.samples import FlowSample


def queue_times(samples: list[FlowSample]) -> list[timedelta]:
    """Queue time per sample that was both started and completed."""
    return [
        s.elapsed(s.arrived_at, s.started_at) + s.wait_time
        for s in samples
        if s.completed_at is not None and s.started_at is not None
    ]


def touch_times(samples: list[FlowSample]) -> list[timedelta]:
    """Active-work time per sample that was both started and completed."""
    result: list[timedelta] = []
    for s in samples:
        if s.completed_at is None or s.started_at is None:
            continue
        cycle = s.elapsed(s.started_at, s.completed_at)
        result.append(cycle - min(s.wait_time, cycle))
    return result
