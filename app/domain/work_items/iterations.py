from collections.abc import Iterable
from datetime import datetime

from app.domain.work_items.entities import Iteration


def current_iteration(iterations: Iterable[Iteration], at: datetime) -> Iteration | None:
    """The iteration running at `at`; in a gap, the next one to start; else None.

    The end instant is exclusive, so it belongs to the following iteration.
    """
    candidates = tuple(iterations)
    running = [i for i in candidates if i.starts_at <= at < i.ends_at]
    if running:
        return min(running, key=lambda i: i.starts_at)
    upcoming = [i for i in candidates if i.starts_at > at]
    return min(upcoming, key=lambda i: i.starts_at, default=None)
