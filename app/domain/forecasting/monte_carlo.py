"""Monte Carlo completion forecasting from historical daily throughput.

Each simulated day draws a completion count uniformly from the scope's
observed daily throughput (zero days included — they carry the real cadence).
Deterministic when seeded, a SPEC requirement: all randomness goes through
random.Random(seed).
"""

import math
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from random import Random

from app.domain.metrics.samples import FlowSample
from app.domain.metrics.stats import percentile

# ponytail: 2k trials keeps the worst case (sparse history hitting MAX_DAYS)
# around a second; raise toward 10k if percentile jitter ever matters.
TRIALS = 2_000
# ponytail: hard cap so a near-zero-throughput history can't spin a trial
# forever; a capped trial reads as "10+ years out", which is answer enough.
MAX_DAYS = 3650


def daily_throughput_samples(
    samples: list[FlowSample], *, end: datetime, days: int
) -> list[int]:
    """Completions per trailing 1-day bucket over (end - days, end], zeros included."""
    counts = [0] * days
    for sample in samples:
        if sample.completed_at is None:
            continue
        age = end - sample.completed_at
        if timedelta(0) <= age < timedelta(days=days):
            counts[age // timedelta(days=1)] += 1
    return counts


def simulate_days_to_complete(
    daily_samples: list[int], *, remaining: int, trials: int = TRIALS, seed: int = 0
) -> list[int] | None:
    """Days to finish `remaining` items, one result per trial.

    Returns None when history holds no completions at all — there is
    nothing to extrapolate from.
    """
    if remaining < 0:
        raise ValueError("remaining must be >= 0")
    if remaining == 0:
        return [0] * trials
    if not any(daily_samples):
        return None
    rng = Random(seed)
    results: list[int] = []
    for _ in range(trials):
        done = 0
        days = 0
        while done < remaining and days < MAX_DAYS:
            done += rng.choice(daily_samples)
            days += 1
        results.append(days)
    return results


@dataclass(frozen=True)
class OutcomeBucket:
    """Number of trials that finished in exactly `days` days."""

    days: int
    trials: int


@dataclass(frozen=True)
class CompletionForecast:
    """Percentile summary + outcome histogram of one simulation run."""

    remaining: int
    trials: int
    p50_days: int
    p75_days: int
    p85_days: int
    p95_days: int
    outcomes: list[OutcomeBucket]


def summarize_completion(days_per_trial: list[int], *, remaining: int) -> CompletionForecast:
    """Fold per-trial durations into ceiling percentiles and an outcome histogram."""
    values = [float(d) for d in days_per_trial]
    counts = Counter(days_per_trial)
    return CompletionForecast(
        remaining=remaining,
        trials=len(days_per_trial),
        p50_days=math.ceil(percentile(values, 50)),
        p75_days=math.ceil(percentile(values, 75)),
        p85_days=math.ceil(percentile(values, 85)),
        p95_days=math.ceil(percentile(values, 95)),
        outcomes=[OutcomeBucket(days=d, trials=n) for d, n in sorted(counts.items())],
    )


def delivery_confidence(days_per_trial: list[int], *, within_days: int) -> float:
    """Share of trials that finished within `within_days` days."""
    if not days_per_trial:
        raise ValueError("delivery_confidence requires at least one trial")
    return sum(1 for d in days_per_trial if d <= within_days) / len(days_per_trial)


@dataclass(frozen=True)
class DeliveryForecast:
    """Scope-level forecast: simulation summary plus optional target confidence.

    window_end doubles as the forecast origin ("now"); completion and
    confidence are None when the scope has no throughput history.
    """

    window_start: datetime
    window_end: datetime
    remaining: int
    completion: CompletionForecast | None
    confidence: float | None
