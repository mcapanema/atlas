"""Blocked Time: total time work items spent explicitly blocked."""

from datetime import timedelta

from app.domain.metrics.samples import FlowSample


def total_blocked_time(samples: list[FlowSample]) -> timedelta:
    """Sum of blocked time across samples."""
    return sum((s.blocked_time for s in samples), timedelta(0))
