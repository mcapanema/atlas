"""Default analysis windows: one source for every layer.

Stat tiles, delivery health, advice and the persisted snapshots read the
trailing STATS_WINDOW_DAYS; the charts (cumulative flow, throughput, the
lead-time distribution) the trailing CHART_WINDOW_DAYS. A request's explicit
window or period overrides both. web/src/lib/windows.ts mirrors these
(pinned by tests/domain/test_windows.py).

One deliberate exception, with no planned fix (ADR-0030): the Bugs
section's chart follows the stats window, not CHART_WINDOW_DAYS, so the
chart and its ratios cover the same days.
"""

STATS_WINDOW_DAYS = 30
CHART_WINDOW_DAYS = 90


def bucketing(window_days: int, daily_max_days: int) -> tuple[int, int]:
    """(count, bucket_days) for the window — daily up to `daily_max_days`, else weekly.

    Weekly count rounds up so the buckets cover the whole window (the oldest
    is clipped to the window start); flooring dropped up to 6 days of
    completions the Throughput tile still counted.
    """
    if window_days <= daily_max_days:
        return window_days, 1
    return -(-window_days // 7), 7
