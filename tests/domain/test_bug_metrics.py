from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.domain.metric_rules.calendar import EVERY_DAY, WorkCalendar
from app.domain.metric_rules.entities import DEFAULT_RULES, MetricRules
from app.domain.metrics.bugs import BugMetrics, compute_bug_metrics
from app.domain.metrics.samples import FlowSample
from app.domain.metrics.throughput import bucketed_throughput
from app.domain.metrics.windows import bucketing
from app.domain.work_items.entities import WorkItem, WorkItemPriority, WorkItemType

# A Friday at noon, so working-day cases cross a weekend.
NOW = datetime(2026, 11, 6, 12, 0, tzinfo=UTC)
TEAM = uuid4()


def _days_ago(days: float) -> datetime:
    return NOW - timedelta(days=days)


def _item(
    *labels: str,
    priority: WorkItemPriority | None = None,
    type_: WorkItemType = WorkItemType.TASK,
) -> WorkItem:
    return WorkItem(team_id=TEAM, title="Item", labels=labels, priority=priority, type=type_)


def _sample(
    created: float,
    completed: float | None = None,
    *,
    canceled: bool = False,
    triage_exit: float | None = None,
    calendar: WorkCalendar = EVERY_DAY,
) -> FlowSample:
    return FlowSample(
        created_at=_days_ago(created),
        started_at=None,
        completed_at=_days_ago(completed) if completed is not None else None,
        blocked_time=timedelta(0),
        canceled=canceled,
        triage_exit_at=_days_ago(triage_exit) if triage_exit is not None else None,
        calendar=calendar,
    )


def _bug(
    created: float,
    completed: float | None = None,
    *,
    priority: WorkItemPriority | None = WorkItemPriority.HIGH,
    canceled: bool = False,
    triage_exit: float | None = None,
    calendar: WorkCalendar = EVERY_DAY,
) -> tuple[WorkItem, FlowSample]:
    sample = _sample(
        created, completed, canceled=canceled, triage_exit=triage_exit, calendar=calendar
    )
    return _item("Bug", priority=priority), sample


def _task(created: float, completed: float | None = None) -> tuple[WorkItem, FlowSample]:
    return _item(), _sample(created, completed)


def _compute(
    items: list[tuple[WorkItem, FlowSample]],
    *,
    rules: MetricRules = DEFAULT_RULES,
    stream_rules: list[MetricRules] | None = None,
    window_days: int = 30,
    data_as_of: datetime | None = None,
) -> BugMetrics:
    return compute_bug_metrics(
        items,
        stream_rules if stream_rules is not None else [rules] * len(items),
        team_rules=rules,
        now=NOW,
        window_days=window_days,
        data_as_of=data_as_of,
    )


def test_bugs_created_in_the_window_count_and_older_ones_do_not() -> None:
    metrics = _compute([_bug(3), _bug(10), _bug(45)])

    assert metrics.created == 2


def test_a_bug_canceled_before_completion_counts_nowhere() -> None:
    metrics = _compute([_bug(3, canceled=True), _bug(5)])

    assert metrics.created == 1
    assert metrics.all_bugs.open == 1


def test_a_bug_done_then_canceled_stays_completed() -> None:
    # Default done_then_canceled="delivered": the sample keeps its completion.
    metrics = _compute([_bug(10, 2, canceled=True)])

    assert (metrics.created, metrics.completed) == (1, 1)


def test_ratios_divide_new_bugs_by_non_bug_completions_and_bugs_by_all() -> None:
    items = [_bug(3), _bug(4), _bug(20, 2), *[_task(40, d) for d in (1, 2, 3)]]

    metrics = _compute(items)

    assert (metrics.created, metrics.completed) == (3, 1)
    assert (metrics.non_bug_completed, metrics.all_completed) == (3, 4)
    assert metrics.per_item == pytest.approx(3 / 3)
    assert metrics.share == pytest.approx(1 / 4)


def test_a_ratio_below_the_floor_keeps_its_value_and_a_zero_denominator_is_none() -> None:
    metrics = _compute([_bug(3), _bug(20, 2)])

    assert metrics.min_sample == DEFAULT_RULES.health_min_sample
    assert metrics.share == 1.0  # 1 of 1: below the floor, still a value
    assert metrics.non_bug_completed == 0
    assert metrics.per_item is None


def test_empty_stream_rules_use_the_team_rules() -> None:
    rules = MetricRules(type_labels=(("defeito", WorkItemType.BUG),))
    item = (_item("defeito"), _sample(3))

    metrics = compute_bug_metrics(
        [item], [], team_rules=rules, now=NOW, window_days=30, data_as_of=None
    )

    assert (metrics.state, metrics.created) == ("ok", 1)


def test_mismatched_stream_rules_raise() -> None:
    with pytest.raises(ValueError, match="stream_rules"):
        compute_bug_metrics(
            [_bug(3), _bug(4)],
            [DEFAULT_RULES],
            team_rules=DEFAULT_RULES,
            now=NOW,
            window_days=30,
            data_as_of=None,
        )


def test_no_mapping_when_no_label_maps_to_bug_and_no_item_is_a_bug() -> None:
    rules = MetricRules(type_labels=(("Feature", WorkItemType.STORY),))

    metrics = _compute([_bug(3), _task(10, 2)], rules=rules)

    assert metrics.state == "no_mapping"
    assert metrics.bug_labels == ()
    assert (metrics.created, metrics.completed, metrics.all_completed) == (0, 0, 0)
    assert metrics.priorities == ()
    assert metrics.buckets == ()


def test_no_matches_when_a_mapping_matches_no_item() -> None:
    rules = MetricRules(type_labels=(("defeito", WorkItemType.BUG),))

    metrics = _compute([_bug(3), _task(10, 2)], rules=rules)

    assert metrics.state == "no_matches"
    assert metrics.bug_labels == ("defeito",)
    assert metrics.created == 0


def test_no_matches_when_an_earlier_entry_claims_the_bug_label() -> None:
    rules = MetricRules(
        type_labels=(("Feature", WorkItemType.STORY), ("bug", WorkItemType.BUG)),
    )
    item = (_item("Feature", "Bug"), _sample(3))

    assert _compute([item], rules=rules).state == "no_matches"


def test_ok_with_no_bug_in_the_window_is_all_zeros() -> None:
    metrics = _compute([_bug(200, 150), _task(10, 2)])

    assert metrics.state == "ok"
    assert (metrics.created, metrics.completed) == (0, 0)
    assert metrics.all_bugs.fixed == 0
    assert metrics.all_bugs.median is None


def test_a_stored_bug_counts_with_no_mapping() -> None:
    rules = MetricRules(type_labels=())
    stored = (_item(type_=WorkItemType.BUG), _sample(3))

    metrics = _compute([stored], rules=rules)

    assert (metrics.state, metrics.created, metrics.bug_labels) == ("ok", 1, ())


def test_an_item_with_no_sample_is_not_in_the_scope() -> None:
    # The service passes only items with a sample; a bug with no events is
    # absent, so the state checks never see it.
    assert _compute([_task(10, 2)]).state == "no_matches"


@pytest.mark.parametrize(("window_days", "bucket_days", "count"), [(7, 1, 7), (30, 7, 5)])
def test_buckets_match_the_throughput_buckets(
    window_days: int, bucket_days: int, count: int
) -> None:
    items = [_bug(0.5, 0.2), _bug(6.5), _bug(29.5, 1), _bug(25, 3)]

    metrics = _compute(items, window_days=window_days)

    assert (metrics.bucket_days, len(metrics.buckets)) == (bucket_days, count)
    expected = bucketed_throughput(
        [sample for _, sample in items],
        end=NOW,
        count=count,
        bucket_days=bucket_days,
        start=NOW - timedelta(days=window_days),
    )
    assert [(b.start, b.end, b.completed) for b in metrics.buckets] == [
        (b.start, b.end, b.completed) for b in expected
    ]
    assert metrics.buckets[0].start == NOW - timedelta(days=window_days)  # oldest clipped


def test_bucket_sums_equal_the_totals() -> None:
    items = [_bug(0.5, 0.2), _bug(6.5), _bug(29.5, 1), _bug(25, 3), _bug(3, canceled=True)]

    metrics = _compute(items)

    assert sum(b.created for b in metrics.buckets) == metrics.created == 4
    assert sum(b.completed for b in metrics.buckets) == metrics.completed == 3


def test_a_bug_counts_as_created_in_the_bucket_holding_its_creation() -> None:
    metrics = _compute([_bug(0.5)], window_days=7)

    [bucket] = [b for b in metrics.buckets if b.created]
    assert bucket.start < _days_ago(0.5) <= bucket.end
    assert bucket == metrics.buckets[-1]


def test_lead_time_counts_working_days() -> None:
    weekdays = WorkCalendar(frozenset({1, 2, 3, 4, 5}))
    # Created Friday noon a week ago, done Monday noon: one working day.
    item = _bug(7, 4, calendar=weekdays)

    metrics = _compute([item])

    assert metrics.all_bugs.median == timedelta(days=1)


def test_lead_time_starts_at_triage_exit_but_created_uses_creation() -> None:
    rules = MetricRules(lead_time_start="triage_exit")
    item = _bug(40, 2, triage_exit=10)

    metrics = _compute([item], rules=rules)

    assert metrics.created == 0  # created 40 days ago, outside the window
    assert metrics.all_bugs.median == timedelta(days=8)


def test_fix_rows_cover_every_priority_in_member_order() -> None:
    items = [
        _bug(20, 2, priority=WorkItemPriority.URGENT),
        _bug(20, 4, priority=WorkItemPriority.URGENT),
        _bug(10, priority=WorkItemPriority.URGENT),
        _bug(15, 5, priority=WorkItemPriority.NONE),
        _bug(30, priority=WorkItemPriority.LOW),
    ]

    metrics = _compute(items)

    assert [priority for priority, _ in metrics.priorities] == list(WorkItemPriority)
    rows = dict(metrics.priorities)
    assert (rows[WorkItemPriority.URGENT].fixed, rows[WorkItemPriority.URGENT].open) == (2, 1)
    assert rows[WorkItemPriority.URGENT].median == timedelta(days=17)  # 18 and 16
    assert rows[WorkItemPriority.URGENT].oldest_open == timedelta(days=10)
    assert rows[WorkItemPriority.HIGH] == rows[WorkItemPriority.MEDIUM]
    assert (rows[WorkItemPriority.HIGH].fixed, rows[WorkItemPriority.HIGH].open) == (0, 0)
    assert rows[WorkItemPriority.HIGH].median is None
    assert rows[WorkItemPriority.HIGH].oldest_open is None
    assert rows[WorkItemPriority.NONE].median == timedelta(days=10)  # one fix, below the floor
    assert rows[WorkItemPriority.LOW].oldest_open == timedelta(days=30)
    assert (metrics.all_bugs.fixed, metrics.all_bugs.open) == (3, 2)
    assert metrics.all_bugs.oldest_open == timedelta(days=30)
    assert metrics.completed == metrics.all_bugs.fixed
    assert metrics.unknown_priority == 0


def test_an_open_bug_still_in_triage_ages_from_creation() -> None:
    rules = MetricRules(lead_time_start="triage_exit")

    metrics = _compute([_bug(12)], rules=rules)

    assert metrics.all_bugs.open == 1
    assert metrics.all_bugs.oldest_open == timedelta(days=12)


def test_an_unknown_priority_counts_in_all_bugs_only() -> None:
    items = [_bug(20, 2, priority=None), _bug(5, priority=None), _bug(50, priority=None)]

    metrics = _compute(items)

    assert (metrics.all_bugs.fixed, metrics.all_bugs.open) == (1, 2)
    assert metrics.unknown_priority == 3
    assert all(stats.fixed == 0 and stats.open == 0 for _, stats in metrics.priorities)
    assert metrics.completed == metrics.all_bugs.fixed


def test_window_and_data_as_of_pass_through() -> None:
    as_of = _days_ago(1)

    metrics = _compute([_bug(3)], data_as_of=as_of)

    assert (metrics.window_start, metrics.window_end) == (_days_ago(30), NOW)
    assert metrics.data_as_of == as_of
    assert metrics.bug_labels == ("bug",)


def test_bucketing_is_daily_up_to_the_cut_over_then_weekly() -> None:
    assert bucketing(21, 21) == (21, 1)
    assert bucketing(30, 21) == (5, 7)
