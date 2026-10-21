"""Flow Efficiency: share of cycle time spent actively working (not waiting)."""

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
        cycle = sample.elapsed(sample.started_at, sample.completed_at).total_seconds()
        if cycle > 0:
            cycles.append((sample, cycle))
    return cycles


def flow_efficiency(samples: list[FlowSample]) -> float | None:
    """Mean of (cycle - wait) / cycle over the measured samples; None without any.

    Wait is blocked time plus time in the team's wait states
    (wait_state_names, ADR-0018).

    ponytail: wait states are a manual per-team list, so a team that lists
    none (and marks no blocked work) still reads close to 100%. Upgrade
    path: suggest likely wait states from state names if unconfigured
    teams prove common.
    """
    ratios = [
        (cycle - min(sample.wait_time.total_seconds(), cycle)) / cycle
        for sample, cycle in measured_cycles(samples)
    ]
    return sum(ratios) / len(ratios) if ratios else None
