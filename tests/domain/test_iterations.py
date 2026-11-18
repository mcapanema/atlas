from datetime import UTC, datetime

import pytest

from app.domain.work_items.entities import Iteration
from app.domain.work_items.iterations import current_iteration

AT = datetime(2026, 11, 17, 12, tzinfo=UTC)
C37 = Iteration(
    "c37", "Cycle 37", datetime(2026, 10, 21, 3, tzinfo=UTC), datetime(2026, 11, 4, 3, tzinfo=UTC)
)
C38 = Iteration(
    "c38", "Cycle 38", datetime(2026, 11, 4, 3, tzinfo=UTC), datetime(2026, 11, 18, 3, tzinfo=UTC)
)
C39 = Iteration(
    "c39", "Cycle 39", datetime(2026, 11, 18, 3, tzinfo=UTC), datetime(2026, 12, 2, 3, tzinfo=UTC)
)


def test_the_iteration_that_contains_the_instant_is_current() -> None:
    assert current_iteration([C37, C39, C38], AT) == C38


def test_the_end_instant_belongs_to_the_next_iteration() -> None:
    assert current_iteration([C38, C39], C38.ends_at) == C39


def test_in_a_gap_the_next_iteration_to_start_is_current() -> None:
    gap = datetime(2026, 11, 3, tzinfo=UTC)
    assert current_iteration([C38, C39], gap) == C38


def test_only_past_iterations_mean_no_current_one() -> None:
    assert current_iteration([C37], AT) is None


def test_no_iterations_mean_no_current_one() -> None:
    assert current_iteration([], AT) is None


def test_an_iteration_must_end_after_it_starts() -> None:
    with pytest.raises(ValueError, match="must end after"):
        Iteration("x", "X", C38.ends_at, C38.starts_at)


def test_an_iteration_needs_aware_datetimes() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        Iteration("x", "X", datetime(2026, 11, 4), datetime(2026, 11, 18))  # noqa: DTZ001 — naive on purpose
