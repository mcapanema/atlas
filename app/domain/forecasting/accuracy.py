"""Forecast accuracy: calibration of past forecasts against actual delivery.

A ForecastSnapshot predicted its scope's `remaining` open items would
finish within pN days of capture. It resolves once `remaining` completions
have landed after the capture instant — the Nth completion dates the
actual finish. Calibration then reads directly: a well-calibrated P85
resolves within its horizon ~85% of the time.

ponytail: completions are counted, not identity-matched — items created
after the capture count toward resolution. That mirrors the Monte Carlo
model itself (it forecasts N completions, not N specific items).
"""

from dataclasses import dataclass
from datetime import datetime
from math import ceil

from app.domain.snapshots.entities import ForecastSnapshot


@dataclass(frozen=True)
class ForecastAccuracy:
    """Aggregate calibration of a scope's resolved past forecasts."""

    evaluated: int
    pending: int
    p50_hit_rate: float | None
    p85_hit_rate: float | None
    mean_abs_error_days: float | None


def evaluate_forecast_accuracy(
    snapshots: list[ForecastSnapshot], completions: list[datetime]
) -> ForecastAccuracy:
    """Resolve each predictive snapshot against completions after its capture.

    Snapshots that predicted nothing (no percentiles, or zero remaining)
    are ignored; unresolved ones count as pending.
    """
    ordered = sorted(completions)
    p50_hits: list[bool] = []
    p85_hits: list[bool] = []
    errors: list[float] = []
    pending = 0
    for snapshot in snapshots:
        if snapshot.p50_days is None or snapshot.p85_days is None:
            continue
        if snapshot.remaining == 0:
            continue
        after = [c for c in ordered if c > snapshot.created_at]
        if len(after) < snapshot.remaining:
            pending += 1
            continue
        finished_at = after[snapshot.remaining - 1]
        actual_days = ceil((finished_at - snapshot.created_at).total_seconds() / 86_400)
        p50_hits.append(actual_days <= snapshot.p50_days)
        p85_hits.append(actual_days <= snapshot.p85_days)
        errors.append(abs(actual_days - snapshot.p50_days))
    evaluated = len(p50_hits)
    return ForecastAccuracy(
        evaluated=evaluated,
        pending=pending,
        p50_hit_rate=sum(p50_hits) / evaluated if evaluated else None,
        p85_hit_rate=sum(p85_hits) / evaluated if evaluated else None,
        mean_abs_error_days=sum(errors) / evaluated if evaluated else None,
    )
