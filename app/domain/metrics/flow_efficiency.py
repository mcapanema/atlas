"""Flow Efficiency: share of cycle time spent actively working (not blocked)."""

from app.domain.metrics.samples import FlowSample


def flow_efficiency(samples: list[FlowSample]) -> float | None:
    """Mean of (cycle - blocked) / cycle over completed samples; None without data.

    ponytail: blocked periods are the only wait signal, so a team that marks
    blocked work by none of the blocked rules (labels, workflow states,
    relations) reads 100%. Count queue-state waiting (e.g. time in Review
    without a reviewer) as wait too if blocked periods prove too coarse.
    """
    ratios: list[float] = []
    for sample in samples:
        if sample.completed_at is None or sample.started_at is None:
            continue
        cycle = (sample.completed_at - sample.started_at).total_seconds()
        if cycle <= 0:
            continue
        blocked = min(sample.blocked_time.total_seconds(), cycle)
        ratios.append((cycle - blocked) / cycle)
    return sum(ratios) / len(ratios) if ratios else None
