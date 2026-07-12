"""Delivery Health: one explainable 0-100 composite per scope.

Five components — predictability, efficiency, flow, stability, risk — each
scored 0-100 with a human-readable reason, averaged into an overall score
and band. Pure arithmetic over already-derived samples and timelines: the
AI layer explains these numbers, it never produces them (VISION:
"AI Explains, Statistics Predict").
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from app.domain.events.entities import Event
from app.domain.events.timeline import derive_timeline
from app.domain.metrics.cycle_time import cycle_times
from app.domain.metrics.flow_efficiency import flow_efficiency
from app.domain.metrics.lead_time import lead_times
from app.domain.metrics.samples import FlowSample, derive_flow_sample
from app.domain.metrics.stats import percentile
from app.domain.metrics.throughput import throughput
from app.domain.metrics.wip import wip

_HEALTHY = 70
_WARNING = 40


@dataclass(frozen=True)
class HealthComponent:
    """One scored dimension of delivery health, with its evidence."""

    name: str
    score: int
    reason: str


@dataclass(frozen=True)
class DeliveryHealth:
    """Composite health for a scope; score/band are None when no component has data."""

    window_start: datetime
    window_end: datetime
    score: int | None
    band: str | None
    components: tuple[HealthComponent, ...]


def _clamp(value: float) -> int:
    return max(0, min(100, round(value)))


def _predictability(lead: list[timedelta]) -> HealthComponent | None:
    """Lead-time spread: p95 at p50 scores 100, p95 at 4x p50 scores 0."""
    if not lead:
        return None
    seconds = [d.total_seconds() for d in lead]
    p50 = percentile(seconds, 50)
    if p50 <= 0:
        return None
    ratio = percentile(seconds, 95) / p50
    return HealthComponent(
        name="predictability",
        score=_clamp(100 * (4 - ratio) / 3),
        reason=f"lead time p95 is {ratio:.1f}x p50",
    )


def _efficiency(in_window: list[FlowSample]) -> HealthComponent | None:
    eff = flow_efficiency(in_window)
    if eff is None:
        return None
    return HealthComponent(
        name="efficiency", score=_clamp(100 * eff), reason=f"flow efficiency {eff:.0%}"
    )


def _flow(
    samples: list[FlowSample], *, window_start: datetime, mid: datetime, now: datetime
) -> HealthComponent | None:
    """Throughput trend: recent half-window vs the half before it."""
    earlier = throughput(samples, start=window_start, end=mid)
    recent = throughput(samples, start=mid, end=now)
    if earlier == 0 and recent == 0:
        return None
    if earlier == 0:
        return HealthComponent(
            name="flow",
            score=100,
            reason=f"throughput grew from 0 to {recent} in the recent half-window",
        )
    return HealthComponent(
        name="flow",
        score=_clamp(100 * recent / earlier),
        reason=f"completed {recent} recently vs {earlier} in the prior half-window",
    )


def _stability(*, wip_now: int, completed: int, window_days: int) -> HealthComponent | None:
    """WIP inventory in weeks of throughput (Little's law): <=1 week 100, >=5 weeks 0."""
    if completed == 0:
        return None
    weekly = completed / (window_days / 7)
    weeks_of_wip = wip_now / weekly
    return HealthComponent(
        name="stability",
        score=_clamp(100 * (5 - weeks_of_wip) / 4),
        reason=f"WIP equals {weeks_of_wip:.1f} weeks of throughput",
    )


def _risk(
    item_states: list[tuple[FlowSample, bool]],
    *,
    now: datetime,
    cycle_p85: timedelta | None,
) -> HealthComponent | None:
    """Share of in-progress items currently blocked or aging past cycle P85."""
    in_progress = [
        (sample, blocked)
        for sample, blocked in item_states
        if sample.started_at is not None
        and sample.started_at <= now
        and (sample.completed_at is None or sample.completed_at > now)
    ]
    if not in_progress:
        return None
    at_risk = sum(
        1
        for sample, blocked in in_progress
        if blocked
        or (
            cycle_p85 is not None
            and sample.started_at is not None
            and now - sample.started_at > cycle_p85
        )
    )
    return HealthComponent(
        name="risk",
        score=_clamp(100 * (1 - at_risk / len(in_progress))),
        reason=(
            f"{at_risk} of {len(in_progress)} in-progress items "
            "blocked or aging past cycle p85"
        ),
    )


def compute_delivery_health(
    streams: list[list[Event]], *, now: datetime, window_days: int = 30
) -> DeliveryHealth:
    """Score the scope's delivery health over the trailing window ending at `now`."""
    window_start = now - timedelta(days=window_days)
    mid = now - timedelta(days=window_days) / 2
    item_states: list[tuple[FlowSample, bool]] = []
    for stream in streams:
        sample = derive_flow_sample(stream)
        if sample is None:
            continue
        ordered = sorted(stream, key=lambda e: e.occurred_at)
        blocked_open = any(
            p.ended_at is None for p in derive_timeline(ordered).blocked_periods
        )
        item_states.append((sample, blocked_open))
    samples = [sample for sample, _ in item_states]
    in_window = [
        s for s in samples if s.completed_at is not None and window_start < s.completed_at <= now
    ]
    completed_cycles = cycle_times(samples)
    cycle_p85 = (
        timedelta(seconds=percentile([c.total_seconds() for c in completed_cycles], 85))
        if completed_cycles
        else None
    )
    components = tuple(
        c
        for c in (
            _predictability(lead_times(in_window)),
            _efficiency(in_window),
            _flow(samples, window_start=window_start, mid=mid, now=now),
            _stability(
                wip_now=wip(samples, at=now), completed=len(in_window), window_days=window_days
            ),
            _risk(item_states, now=now, cycle_p85=cycle_p85),
        )
        if c is not None
    )
    if not components:
        return DeliveryHealth(
            window_start=window_start, window_end=now, score=None, band=None, components=()
        )
    score = round(sum(c.score for c in components) / len(components))
    band = "healthy" if score >= _HEALTHY else "warning" if score >= _WARNING else "critical"
    return DeliveryHealth(
        window_start=window_start, window_end=now, score=score, band=band, components=components
    )
