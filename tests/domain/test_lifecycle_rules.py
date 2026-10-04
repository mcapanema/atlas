from datetime import UTC, date, datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

from app.domain.events.entities import Event, EventType
from app.domain.metric_rules.entities import MetricRules
from app.domain.metrics.cfd import daily_flow_counts
from app.domain.metrics.samples import derive_flow_sample, in_progress

ITEM = uuid4()


def _june(day: int) -> datetime:
    return datetime(2026, 6, day, tzinfo=UTC)


def _on(type_: EventType, day: int) -> Event:
    return Event(work_item_id=ITEM, type=type_, occurred_at=_june(day))


PARKED = [
    _on(EventType.CREATED, 1),
    _on(EventType.STARTED, 2),
    _on(EventType.STOPPED, 4),
    _on(EventType.STARTED, 10),
    _on(EventType.COMPLETED, 12),
]
REOPENED = [
    _on(EventType.CREATED, 1),
    _on(EventType.STARTED, 2),
    _on(EventType.COMPLETED, 5),
    _on(EventType.STARTED, 7),
    _on(EventType.COMPLETED, 9),
]
CANCELED_AFTER_DONE = [
    _on(EventType.CREATED, 1),
    _on(EventType.STARTED, 2),
    _on(EventType.COMPLETED, 5),
    _on(EventType.CANCELED, 6),
]


def test_by_default_a_restart_keeps_the_first_start() -> None:
    sample = derive_flow_sample(PARKED)

    assert sample is not None
    assert sample.started_at == _june(2)


def test_restart_clock_rule_starts_the_cycle_at_the_restart() -> None:
    sample = derive_flow_sample(PARKED, MetricRules(restart_clock_after_move_back=True))

    assert sample is not None
    assert (sample.started_at, sample.completed_at) == (_june(10), _june(12))


def test_restart_clock_rule_ignores_reopens_after_done() -> None:
    sample = derive_flow_sample(REOPENED, MetricRules(restart_clock_after_move_back=True))

    assert sample is not None
    assert sample.started_at == _june(2)


def test_move_back_does_not_end_wip_when_the_rule_is_off() -> None:
    events = [_on(EventType.CREATED, 1), _on(EventType.STARTED, 2), _on(EventType.STOPPED, 4)]

    default = derive_flow_sample(events)
    kept = derive_flow_sample(events, MetricRules(move_back_ends_wip=False))

    assert default is not None
    assert kept is not None
    assert not in_progress(default, _june(5))
    assert kept.stopped_at is None
    assert in_progress(kept, _june(5))


def test_reopen_completion_first_measures_to_the_first_completion() -> None:
    last = derive_flow_sample(REOPENED)
    first = derive_flow_sample(REOPENED, MetricRules(reopen_completion="first"))

    assert last is not None
    assert first is not None
    assert (last.completed_at, first.completed_at) == (_june(9), _june(5))


def test_reopen_completion_first_still_voids_an_open_reopen() -> None:
    sample = derive_flow_sample(REOPENED[:4], MetricRules(reopen_completion="first"))

    assert sample is not None
    assert sample.completed_at is None


def test_first_completion_never_precedes_a_restarted_clock() -> None:
    events = [
        _on(EventType.CREATED, 1),
        _on(EventType.STARTED, 2),
        _on(EventType.COMPLETED, 3),
        _on(EventType.STARTED, 4),
        _on(EventType.STOPPED, 5),
        _on(EventType.STARTED, 6),
        _on(EventType.COMPLETED, 8),
    ]
    rules = MetricRules(restart_clock_after_move_back=True, reopen_completion="first")

    sample = derive_flow_sample(events, rules)

    assert sample is not None
    assert (sample.started_at, sample.completed_at) == (_june(6), _june(8))


def test_done_then_canceled_stays_delivered_by_default() -> None:
    sample = derive_flow_sample(CANCELED_AFTER_DONE)

    assert sample is not None
    assert sample.completed_at == _june(5)
    assert not sample.canceled


def test_done_then_canceled_rule_undelivers() -> None:
    sample = derive_flow_sample(CANCELED_AFTER_DONE, MetricRules(done_then_canceled="canceled"))

    assert sample is not None
    assert sample.completed_at is None
    assert sample.canceled
    assert sample.stopped_at == _june(6)


def test_cfd_follows_the_done_then_canceled_rule() -> None:
    days = daily_flow_counts(
        [CANCELED_AFTER_DONE],
        start=_june(5),
        end=_june(7),
        stream_rules=[MetricRules(done_then_canceled="canceled")],
    )

    assert [d.done for d in days] == [1, 0, 0]


def test_cfd_keeps_moved_back_items_in_progress_when_the_rule_is_off() -> None:
    events = [_on(EventType.CREATED, 1), _on(EventType.STARTED, 2), _on(EventType.STOPPED, 4)]

    days = daily_flow_counts(
        [events],
        start=_june(3),
        end=_june(5),
        stream_rules=[MetricRules(move_back_ends_wip=False)],
    )

    assert [d.in_progress for d in days] == [1, 1, 1]


def test_cfd_days_follow_the_scope_timezone() -> None:
    sao_paulo = ZoneInfo("America/Sao_Paulo")  # UTC-3, no DST
    done_late_evening = [
        Event(
            work_item_id=ITEM,
            type=EventType.CREATED,
            occurred_at=datetime(2026, 7, 1, 12, tzinfo=UTC),
        ),
        # 22:00 on 4 July in São Paulo, already 5 July in UTC.
        Event(
            work_item_id=ITEM,
            type=EventType.COMPLETED,
            occurred_at=datetime(2026, 7, 5, 1, tzinfo=UTC),
        ),
    ]
    start = datetime(2026, 7, 4, 3, tzinfo=UTC)  # local midnight, 4 July
    end = datetime(2026, 7, 6, 3, tzinfo=UTC)

    local = daily_flow_counts([done_late_evening], start=start, end=end, tz=sao_paulo)
    utc = daily_flow_counts([done_late_evening], start=start, end=end)

    assert (local[0].day, local[0].done) == (date(2026, 7, 4), 1)
    assert (utc[0].day, utc[0].done) == (date(2026, 7, 4), 0)


def test_cfd_day_ends_after_the_repeated_hour_when_dst_ends_at_midnight() -> None:
    santiago = ZoneInfo("America/Santiago")  # 4 Apr 2026: 24:00 -> 23:00, 23:xx repeats
    events = [
        Event(
            work_item_id=ITEM,
            type=EventType.CREATED,
            occurred_at=datetime(2026, 4, 1, 12, tzinfo=UTC),
        ),
        # 23:30 on 4 April, second occurrence (UTC-4).
        Event(
            work_item_id=ITEM,
            type=EventType.COMPLETED,
            occurred_at=datetime(2026, 4, 5, 3, 30, tzinfo=UTC),
        ),
    ]
    start = datetime(2026, 4, 4, 3, tzinfo=UTC)  # local midnight, 4 April (UTC-3)
    end = datetime(2026, 4, 7, 4, tzinfo=UTC)

    days = daily_flow_counts([events], start=start, end=end, tz=santiago)

    assert (days[0].day, days[0].done) == (date(2026, 4, 4), 1)


def test_restart_after_done_then_canceled_opens_a_new_stint() -> None:
    events = [
        _on(EventType.CREATED, 1),
        _on(EventType.STARTED, 2),
        _on(EventType.COMPLETED, 5),
        _on(EventType.CANCELED, 6),
        _on(EventType.STARTED, 8),
    ]
    rules = MetricRules(done_then_canceled="canceled", restart_clock_after_move_back=True)

    sample = derive_flow_sample(events, rules)

    assert sample is not None
    assert (sample.started_at, sample.completed_at, sample.canceled) == (_june(8), None, False)


def test_restart_clock_without_move_back_ending_wip_restarts_only_after_a_cancel() -> None:
    events = [
        _on(EventType.CREATED, 1),
        _on(EventType.STARTED, 2),
        _on(EventType.STOPPED, 4),
        _on(EventType.STARTED, 6),
        _on(EventType.CANCELED, 7),
        _on(EventType.STARTED, 9),
    ]
    rules = MetricRules(move_back_ends_wip=False, restart_clock_after_move_back=True)

    after_stop = derive_flow_sample(events[:4], rules)
    after_cancel = derive_flow_sample(events, rules)

    assert after_stop is not None
    assert after_cancel is not None
    assert after_stop.started_at == _june(2)  # the STOPPED was ignored: no restart
    assert after_cancel.started_at == _june(9)  # only a CANCELED restarts
