"""Percentiles for metric distributions."""

import statistics
from collections.abc import Sequence


def percentile(values: Sequence[float], p: int) -> float:
    """Linear-interpolated p-th percentile (1 <= p <= 99) of a non-empty sequence."""
    if not values:
        raise ValueError("percentile requires at least one value")
    if not 1 <= p <= 99:
        raise ValueError("p must be between 1 and 99")
    if len(values) == 1:
        return float(values[0])
    return statistics.quantiles(values, n=100, method="inclusive")[p - 1]
