"""Flow Efficiency: share of cycle time spent actively working (not blocked)."""

from app.domain.metrics.samples import FlowSample


def flow_efficiency(samples: list[FlowSample]) -> float | None:
    """Mean of (cycle - blocked) / cycle over completed samples; None without data.

    ponytail: blocked periods are the only wait signal today, so data without
    BLOCKED events reads 100%. Count queue-state waiting (e.g. time in Review
    without a reviewer) once workflow states carry a type/category the domain
    can tell apart.
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
