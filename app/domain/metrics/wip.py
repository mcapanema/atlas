"""WIP: work items in progress at a point in time.

In progress means started and not yet completed, moved back, or canceled.
"""

from datetime import datetime

from app.domain.metrics.samples import FlowSample, in_progress


def wip(samples: list[FlowSample], *, at: datetime) -> int:
    """Count samples in progress at `at` (see `in_progress`).

    ponytail: a reopened item's completed_at/stopped_at is voided, so it
    counts as WIP "now" (true) but also for past instants where it was
    actually done or parked — fine for the current-WIP stat this feeds; the
    CFD replays full event history for past days.
    """
    return sum(1 for sample in samples if in_progress(sample, at))
