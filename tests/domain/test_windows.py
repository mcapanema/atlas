import re
from pathlib import Path

from app.domain.metrics.windows import CHART_WINDOW_DAYS, STATS_WINDOW_DAYS


def test_default_windows() -> None:
    assert (STATS_WINDOW_DAYS, CHART_WINDOW_DAYS) == (30, 90)


def test_the_frontend_mirrors_the_backend_windows() -> None:
    # The SPA can't import Python; this pins its one copy to the source.
    windows_ts = Path(__file__).resolve().parents[2] / "web" / "src" / "lib" / "windows.ts"
    source = windows_ts.read_text()

    assert re.search(
        rf"^export const STATS_WINDOW_DAYS = {STATS_WINDOW_DAYS};$", source, re.MULTILINE
    )
    assert re.search(
        rf"^export const CHART_WINDOW_DAYS = {CHART_WINDOW_DAYS};$", source, re.MULTILINE
    )
