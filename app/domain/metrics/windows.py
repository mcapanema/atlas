"""Default analysis windows: one source for every layer.

Stat tiles, delivery health, advice and the persisted snapshots read the
trailing STATS_WINDOW_DAYS; the charts (cumulative flow, throughput, the
lead-time distribution) the trailing CHART_WINDOW_DAYS. A request's explicit
window or period overrides both. web/src/lib/windows.ts mirrors these
(pinned by tests/domain/test_windows.py).
"""

STATS_WINDOW_DAYS = 30
CHART_WINDOW_DAYS = 90
