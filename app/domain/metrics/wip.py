"""WIP: work items started but not completed at a point in time."""

from datetime import datetime

from app.domain.metrics.samples import FlowSample


def wip(samples: list[FlowSample], *, at: datetime) -> int:
    """Count samples in progress at `at`: started on or before it, not completed by it.

    ponytail: a reopened item's completed_at is voided, so it counts as WIP
    "now" (true) but also for past instants where it was actually done —
    fine for the current-WIP stat this feeds; derive WIP history from full
    event replay when Phase 4's CFD needs it.
    """
    count = 0
    for sample in samples:
        if sample.started_at is None or sample.started_at > at:
            continue
        if sample.completed_at is not None and sample.completed_at <= at:
            continue
        count += 1
    return count
