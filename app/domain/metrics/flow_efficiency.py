"""Flow Efficiency: share of cycle time spent actively working (not blocked)."""

from app.domain.metrics.samples import FlowSample


def measured_cycles(samples: list[FlowSample]) -> list[tuple[FlowSample, float]]:
    """(sample, cycle seconds) for each sample flow efficiency measures.

    Completed samples with a cycle longer than zero: one started and
    completed in the same instant (an automation) has no ratio to measure.
    """
    cycles: list[tuple[FlowSample, float]] = []
    for sample in samples:
        if sample.completed_at is None or sample.started_at is None:
            continue
        cycle = (sample.completed_at - sample.started_at).total_seconds()
        if cycle > 0:
            cycles.append((sample, cycle))
    return cycles


def flow_efficiency(samples: list[FlowSample]) -> float | None:
    """Mean of (cycle - blocked) / cycle over the measured samples; None without any.

    ponytail: blocked periods are the only wait signal, so a team that marks
    blocked work by none of the blocked rules (labels, workflow states,
    relations) reads 100%. Count queue-state waiting (e.g. time in Review
    without a reviewer) as wait too if blocked periods prove too coarse.
    """
    ratios = [
        (cycle - min(sample.blocked_time.total_seconds(), cycle)) / cycle
        for sample, cycle in measured_cycles(samples)
    ]
    return sum(ratios) / len(ratios) if ratios else None
