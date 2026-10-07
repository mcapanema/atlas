from dataclasses import replace
from datetime import UTC, date, datetime, time
from typing import Any
from uuid import uuid4

import pytest

from app.domain.sync_schedules.entities import SyncRun, SyncSchedule
from app.domain.sync_schedules.slots import due_slot, latest_slot, next_slot, slots_on

WEEKDAYS = frozenset({1, 2, 3, 4, 5})

# Mon-Fri, 08:00-18:00 every 2 h in São Paulo (UTC-3, no DST): local slots
# 08, 10, 12, 14, 16, 18 are 11, 13, 15, 17, 19, 21 UTC. 2026-10-05 is a Monday.
BASE = SyncSchedule(
    organization_id=uuid4(),
    enabled=True,
    days=WEEKDAYS,
    window_start=time(8, 0),
    window_end=time(18, 0),
    interval_minutes=120,
    timezone="America/Sao_Paulo",
    updated_at=datetime(2026, 10, 1, tzinfo=UTC),
)


def _schedule(**changes: Any) -> SyncSchedule:
    return replace(BASE, **changes)  # re-runs __post_init__, so invariants apply


def _utc(day: int, hour: int, minute: int = 0, *, month: int = 10) -> datetime:
    return datetime(2026, month, day, hour, minute, tzinfo=UTC)


# --- invariants -------------------------------------------------------------


def test_valid_schedule_keeps_its_settings() -> None:
    schedule = _schedule()

    assert schedule.days == WEEKDAYS
    assert schedule.timezone == "America/Sao_Paulo"
    assert schedule.last_run is None


@pytest.mark.parametrize("days", [frozenset({0}), frozenset({8}), frozenset({1, 9})])
def test_days_must_be_iso_weekdays(days: frozenset[int]) -> None:
    with pytest.raises(ValueError, match="ISO weekdays"):
        _schedule(days=days)


def test_enabled_schedule_needs_a_day() -> None:
    with pytest.raises(ValueError, match="at least one day"):
        _schedule(days=frozenset())


def test_disabled_schedule_may_have_no_days() -> None:
    assert _schedule(enabled=False, days=frozenset()).days == frozenset()


def test_window_must_not_wrap_past_midnight() -> None:
    with pytest.raises(ValueError, match="overnight"):
        _schedule(window_start=time(22, 0), window_end=time(2, 0))


def test_window_may_be_a_single_instant() -> None:
    assert _schedule(window_start=time(9, 0), window_end=time(9, 0)).window_end == time(9, 0)


@pytest.mark.parametrize("moment", [time(8, 0, 30), time(8, 0, 0, 5), time(8, 0, tzinfo=UTC)])
def test_window_times_are_whole_local_minutes(moment: time) -> None:
    with pytest.raises(ValueError, match="whole minutes"):
        _schedule(window_start=moment)


@pytest.mark.parametrize("minutes", [0, 14, 1441])
def test_interval_is_bounded(minutes: int) -> None:
    with pytest.raises(ValueError, match="between 15 and 1440"):
        _schedule(interval_minutes=minutes)


@pytest.mark.parametrize("zone", ["Mars/Base", "", "../etc/passwd"])
def test_timezone_must_be_a_known_iana_zone(zone: str) -> None:
    with pytest.raises(ValueError, match="Unknown timezone"):
        _schedule(timezone=zone)


def test_updated_at_must_be_timezone_aware() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        _schedule(updated_at=_utc(1, 0).replace(tzinfo=None))


# --- slots --------------------------------------------------------------------


def test_slots_run_from_window_start_every_interval_through_window_end() -> None:
    assert slots_on(_schedule(), date(2026, 10, 7)) == [
        _utc(7, hour) for hour in (11, 13, 15, 17, 19, 21)
    ]


def test_no_slots_on_an_unselected_day() -> None:
    assert slots_on(_schedule(), date(2026, 10, 10)) == []  # Saturday


def test_window_end_off_the_interval_grid_is_not_a_slot() -> None:
    schedule = _schedule(window_start=time(8, 0), window_end=time(9, 0), interval_minutes=45)

    assert slots_on(schedule, date(2026, 10, 7)) == [_utc(7, 11), _utc(7, 11, 45)]


def test_single_instant_window_is_one_daily_slot() -> None:
    schedule = _schedule(window_start=time(7, 0), window_end=time(7, 0))

    assert slots_on(schedule, date(2026, 10, 7)) == [_utc(7, 10)]


def test_spring_forward_gap_yields_each_instant_once() -> None:
    # New York skips 02:00-03:00 on Sunday 2026-03-08: local 02:00 and 03:00
    # are the same instant (07:00 UTC), so they collapse into one slot.
    schedule = _schedule(
        days=frozenset({7}),
        window_start=time(1, 0),
        window_end=time(4, 0),
        interval_minutes=60,
        timezone="America/New_York",
    )

    assert slots_on(schedule, date(2026, 3, 8)) == [
        _utc(8, 6, month=3),
        _utc(8, 7, month=3),
        _utc(8, 8, month=3),
    ]


def test_fall_back_repeats_no_slot() -> None:
    # New York repeats 01:00-02:00 on Sunday 2026-11-01; local 01:00 fires
    # once, at its first occurrence (EDT, 05:00 UTC).
    schedule = _schedule(
        days=frozenset({7}),
        window_start=time(0, 0),
        window_end=time(3, 0),
        interval_minutes=60,
        timezone="America/New_York",
    )

    assert slots_on(schedule, date(2026, 11, 1)) == [
        _utc(1, 4, month=11),
        _utc(1, 5, month=11),
        _utc(1, 7, month=11),
        _utc(1, 8, month=11),
    ]


def test_latest_slot_is_the_last_one_at_or_before_now() -> None:
    assert latest_slot(_schedule(), _utc(7, 14)) == _utc(7, 13)
    assert latest_slot(_schedule(), _utc(7, 13)) == _utc(7, 13)


def test_latest_slot_reaches_back_over_the_weekend() -> None:
    # Monday 07:00 local, before the window opens: Friday's last slot.
    assert latest_slot(_schedule(), _utc(12, 10)) == _utc(9, 21)


def test_slots_follow_the_local_date_not_the_utc_date() -> None:
    # Thursday 01:00 UTC is still Wednesday 22:00 in São Paulo.
    now = _utc(8, 1)

    assert latest_slot(_schedule(), now) == _utc(7, 21)
    assert next_slot(_schedule(), now) == _utc(8, 11)


def test_next_slot_skips_unselected_days() -> None:
    # Friday 19:00 local, after the window: Monday's first slot.
    assert next_slot(_schedule(), _utc(9, 22)) == _utc(12, 11)


def test_disabled_schedule_has_no_next_or_due_slot() -> None:
    schedule = _schedule(enabled=False)

    assert next_slot(schedule, _utc(7, 12)) is None
    assert due_slot(schedule, _utc(7, 12)) is None


# --- due ----------------------------------------------------------------------


def test_due_slot_is_the_latest_slot_since_the_last_save() -> None:
    schedule = _schedule(updated_at=_utc(7, 10, 30))

    assert due_slot(schedule, _utc(7, 13, 5)) == _utc(7, 13)


def test_slots_before_the_last_save_never_fire() -> None:
    # Saved at 10:30 local, after the 10:00 slot: nothing until 12:00.
    schedule = _schedule(updated_at=_utc(7, 13, 30))

    assert due_slot(schedule, _utc(7, 13, 45)) is None
    assert due_slot(schedule, _utc(7, 15)) == _utc(7, 15)


def test_a_slot_already_run_is_not_due_again() -> None:
    run = SyncRun(slot_at=_utc(7, 13), finished_at=_utc(7, 13, 2))
    schedule = _schedule(last_run=run)

    assert due_slot(schedule, _utc(7, 14)) is None
    assert due_slot(schedule, _utc(7, 15, 1)) == _utc(7, 15)


def test_slots_missed_while_atlas_was_off_collapse_into_one_catch_up() -> None:
    # Last ran Monday 18:00 local; Atlas comes back Friday 09:00 local. Only
    # Friday's 08:00 slot is due, not every slot of Tue-Thu.
    run = SyncRun(slot_at=_utc(5, 21), finished_at=_utc(5, 21, 1))
    schedule = _schedule(last_run=run)

    assert due_slot(schedule, _utc(9, 12)) == _utc(9, 11)
