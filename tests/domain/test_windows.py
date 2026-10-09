import re
from pathlib import Path

from app.domain.metrics.windows import CHART_WINDOW_DAYS, STATS_WINDOW_DAYS


def test_default_windows() -> None:
    assert (STATS_WINDOW_DAYS, CHART_WINDOW_DAYS) == (30, 90)


def test_the_frontend_mirrors_the_backend_windows() -> None:
    # The SPA can't import Python; this pins its one copy to the source.
    source = Path("web/src/lib/windows.ts").read_text()

    assert re.search(rf"STATS_WINDOW_DAYS = {STATS_WINDOW_DAYS};", source)
    assert re.search(rf"CHART_WINDOW_DAYS = {CHART_WINDOW_DAYS};", source)
