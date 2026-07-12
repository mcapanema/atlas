from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.domain.metrics.aging import compute_aging_wip
from app.domain.metrics.samples import FlowSample
from app.domain.work_items.entities import WorkItem

NOW = datetime(2026, 7, 10, tzinfo=UTC)


def _pair(
    title: str, *, started_days: int | None, completed_days: int | None
) -> tuple[WorkItem, FlowSample]:
    item = WorkItem(team_id=uuid4(), title=title, state="in_progress")
    sample = FlowSample(
        created_at=NOW - timedelta(days=30),
        started_at=NOW - timedelta(days=started_days) if started_days is not None else None,
        completed_at=(
            NOW - timedelta(days=completed_days) if completed_days is not None else None
        ),
        blocked_time=timedelta(0),
    )
    return item, sample


def test_lists_in_progress_items_oldest_first_with_p85_flag() -> None:
    old = _pair("Old", started_days=10, completed_days=None)
    young = _pair("Young", started_days=2, completed_days=None)
    done = _pair("Done", started_days=8, completed_days=1)  # cycle = 7d -> p85 = 7d

    aging = compute_aging_wip([young, done, old], now=NOW)

    assert aging.cycle_time_p85 == timedelta(days=7)
    assert [a.title for a in aging.items] == ["Old", "Young"]
    assert aging.items[0].age == timedelta(days=10)
    assert aging.items[0].over_p85 is True
    assert aging.items[1].over_p85 is False
    assert aging.items[0].work_item_id == old[0].id


def test_no_completed_history_means_no_p85_and_no_flags() -> None:
    doing = _pair("Doing", started_days=5, completed_days=None)

    aging = compute_aging_wip([doing], now=NOW)

    assert aging.cycle_time_p85 is None
    assert aging.items[0].over_p85 is False


def test_unstarted_and_completed_items_are_excluded() -> None:
    backlog = _pair("Backlog", started_days=None, completed_days=None)
    done = _pair("Done", started_days=8, completed_days=1)

    aging = compute_aging_wip([backlog, done], now=NOW)

    assert aging.items == ()
