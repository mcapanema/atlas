"""Delivery Health: one explainable 0-100 composite per scope.

Five components — predictability, efficiency, flow, stability, risk — each
scored 0-100 with a human-readable reason, weighted into an overall score
and band; efficiency carries no weight by default. Pure arithmetic over
already-derived samples and timelines: the AI layer explains these
numbers, it never produces them (VISION: "AI Explains, Statistics
Predict"). Scales, the aging percentile and history, component weights and
band cutoffs come from the scope's MetricRules; the cutoffs band each
component as well as the overall score. A component backed by fewer than
the rules' health_min_sample items is left out; with none left the scope
is unscored, not critical.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timedelta

from app.domain.events.entities import Event
from app.domain.metric_rules.entities import DEFAULT_RULES, MetricRules
from app.domain.metrics.aging import aging_reference
from app.domain.metrics.flow_efficiency import flow_efficiency, measured_cycles
from app.domain.metrics.lead_time import lead_times
from app.domain.metrics.samples import (
    FlowSample,
    derive_flow_sample,
    in_progress,
    observed_history_days,
)
from app.domain.metrics.stats import percentile
from app.domain.metrics.throughput import throughput
from app.domain.metrics.windows import STATS_WINDOW_DAYS
from app.domain.metrics.wip import wip


@dataclass(frozen=True)
class HealthComponent:
    """One scored dimension of delivery health, with its evidence.

    `band` reads the score against the scope's cutoffs, the same rule as
    the overall band, so a weak component shows on a healthy team. Scoring
    sets it; it is None only on a component that hasn't been scored yet.
    """

    name: str
    score: int
    reason: str
    band: str | None = None


@dataclass(frozen=True)
class DeliveryHealth:
    """Composite health for a scope; score/band are None when no component has enough data."""

    window_start: datetime
    window_end: datetime
    score: int | None
    band: str | None
    components: tuple[HealthComponent, ...]


def _clamp(value: float) -> int:
    return max(0, min(100, round(value)))


def _predictability(
    lead: list[timedelta], *, worst_ratio: float, min_sample: int
) -> HealthComponent | None:
    """Lead-time spread on a log scale: p95 at p50 scores 100, at `worst_ratio` x p50 scores 0.

    Log, because the spread is a ratio: each doubling of p95/p50 costs the
    same points, so a team going from 16x to 8x gains as much as one going
    from 2x to 1x. A linear 4x scale pinned 7 of 9 live teams at 0.
    """
    if len(lead) < min_sample:
        return None
    seconds = [d.total_seconds() for d in lead]
    p50 = percentile(seconds, 50)
    if p50 <= 0:
        return None
    ratio = percentile(seconds, 95) / p50
    return HealthComponent(
        name="predictability",
        score=_clamp(100 * (1 - math.log(ratio) / math.log(worst_ratio))),
        reason=f"lead time p95 is {ratio:.1f}x p50",
    )


def _efficiency(in_window: list[FlowSample], *, min_sample: int) -> HealthComponent | None:
    if len(measured_cycles(in_window)) < min_sample:
        return None
    eff = flow_efficiency(in_window)
    if eff is None:
        return None
    return HealthComponent(
        name="efficiency", score=_clamp(100 * eff), reason=f"flow efficiency {eff:.0%}"
    )


def _flow(
    samples: list[FlowSample],
    *,
    window_start: datetime,
    mid: datetime,
    now: datetime,
    min_sample: int,
) -> HealthComponent | None:
    """Throughput trend: recent half-window vs the half before it.

    The caller leaves it out when the tracked history doesn't cover the whole window.
    """
    earlier = throughput(samples, start=window_start, end=mid)
    recent = throughput(samples, start=mid, end=now)
    if earlier + recent < min_sample:
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


def _stability(
    *,
    wip_now: int,
    completed: int,
    tracked_days: int,
    best_weeks: float,
    worst_weeks: float,
    min_sample: int,
) -> HealthComponent | None:
    """WIP inventory in weeks of throughput (Little's law): <= best 100, >= worst 0.

    Throughput is per *tracked* week: a scope first synced mid-window
    completed its items in fewer days than the window spans.
    """
    if completed < min_sample:
        return None
    weekly = completed / (tracked_days / 7)
    weeks_of_wip = wip_now / weekly
    return HealthComponent(
        name="stability",
        score=_clamp(100 * (worst_weeks - weeks_of_wip) / (worst_weeks - best_weeks)),
        reason=f"WIP equals {weeks_of_wip:.1f} weeks of throughput",
    )


def _risk(
    item_states: list[tuple[FlowSample, bool]],
    *,
    now: datetime,
    aging_limit: tuple[timedelta, str],
    min_sample: int,
) -> HealthComponent | None:
    """Share of in-progress items currently blocked or in progress past `aging_limit`.

    `aging_limit` is (limit, how the reason names it) — see `_aging_limit`.
    """
    cycle_limit, limit_label = aging_limit
    open_items = [(sample, blocked) for sample, blocked in item_states if in_progress(sample, now)]
    if len(open_items) < min_sample:
        return None
    at_risk = sum(
        1
        for sample, blocked in open_items
        if blocked or (sample.started_at is not None and now - sample.started_at > cycle_limit)
    )
    return HealthComponent(
        name="risk",
        score=_clamp(100 * (1 - at_risk / len(open_items))),
        reason=f"{at_risk} of {len(open_items)} in-progress items blocked or {limit_label}",
    )


def _aging_limit(
    samples: list[FlowSample], *, now: datetime, rules: MetricRules
) -> tuple[timedelta, str]:
    """The risk component's aging limit and how its reason names it.

    The cycle-time percentile over the aging history; with nothing completed
    in that history, the history itself — an item in progress longer than
    the whole history, with nothing finished in it, is aging by any measure.
    The Aging WIP card keeps no flags in that case (its line is the percentile).
    """
    reference = aging_reference(
        samples, now=now, pct=rules.aging_percentile, history_days=rules.aging_history_days
    )
    if reference is not None:
        return reference, f"aging past cycle p{rules.aging_percentile}"
    return (
        timedelta(days=rules.aging_history_days),
        f"in progress over {rules.aging_history_days} days with nothing completed in them",
    )


def _item_states(
    streams: list[list[Event]], samples: Sequence[FlowSample | None] | None
) -> list[tuple[FlowSample, bool]]:
    """(sample, blocked right now) per item; samples derived with built-in rules if absent."""
    derived = samples if samples is not None else [derive_flow_sample(s) for s in streams]
    return [(sample, sample.blocked_now) for sample in derived if sample is not None]


def _band(score: int, rules: MetricRules) -> str:
    if score >= rules.healthy_min:
        return "healthy"
    if score >= rules.warning_min:
        return "warning"
    return "critical"


def _score(
    components: tuple[HealthComponent, ...], rules: MetricRules
) -> tuple[tuple[HealthComponent, ...], int | None, str | None]:
    """Weighted overall score and band; kept components banded, zero-weight ones dropped."""
    weighted = tuple(
        replace(c, band=_band(c.score, rules)) for c in components if rules.weight(c.name) > 0
    )
    if not weighted:
        return (), None, None
    total = sum(rules.weight(c.name) for c in weighted)
    score = round(sum(c.score * rules.weight(c.name) for c in weighted) / total)
    return weighted, score, _band(score, rules)


def compute_delivery_health(
    streams: list[list[Event]],
    *,
    now: datetime,
    window_days: int = STATS_WINDOW_DAYS,
    samples: Sequence[FlowSample | None] | None = None,
    rules: MetricRules = DEFAULT_RULES,
) -> DeliveryHealth:
    """Score the scope's delivery health over the trailing window ending at `now`.

    `samples` are the streams' samples (aligned by index) when the caller
    folded them with per-item rules; omitted, they're derived with the
    built-in rules. `rules` are the scope's.
    """
    window_start = now - timedelta(days=window_days)
    mid = now - timedelta(days=window_days) / 2
    item_states = _item_states(streams, samples)
    all_samples = [sample for sample, _ in item_states]
    in_window = [
        s
        for s in all_samples
        if s.completed_at is not None and window_start < s.completed_at <= now
    ]
    # A scope first synced mid-window has no earlier half to compare
    # (it read "grew from 0"), and fewer days of throughput than the window.
    tracked_days = observed_history_days(all_samples, end=now, days=window_days)
    floor = rules.health_min_sample
    candidates = (
        _predictability(
            lead_times(in_window), worst_ratio=rules.predictability_worst_ratio, min_sample=floor
        ),
        _efficiency(in_window, min_sample=floor),
        (
            _flow(all_samples, window_start=window_start, mid=mid, now=now, min_sample=floor)
            if tracked_days >= window_days
            else None
        ),
        _stability(
            wip_now=wip(all_samples, at=now),
            completed=len(in_window),
            tracked_days=tracked_days,
            best_weeks=rules.stability_best_weeks,
            worst_weeks=rules.stability_worst_weeks,
            min_sample=floor,
        ),
        _risk(
            item_states,
            now=now,
            aging_limit=_aging_limit(all_samples, now=now, rules=rules),
            min_sample=floor,
        ),
    )
    components, score, band = _score(tuple(c for c in candidates if c is not None), rules)
    return DeliveryHealth(
        window_start=window_start, window_end=now, score=score, band=band, components=components
    )
