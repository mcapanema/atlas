from datetime import UTC, date, datetime, timedelta

from app.domain.metric_rules.calendar import EVERY_DAY, WorkCalendar

WEEKDAYS = WorkCalendar(frozenset({1, 2, 3, 4, 5}))


def test_every_day_is_plain_subtraction() -> None:
    a, b = datetime(2026, 10, 16, 18, tzinfo=UTC), datetime(2026, 10, 19, 10, tzinfo=UTC)
    assert EVERY_DAY.elapsed(a, b) == b - a


def test_friday_evening_to_monday_morning_skips_the_weekend() -> None:
    assert WEEKDAYS.elapsed(
        datetime(2026, 10, 16, 18, tzinfo=UTC), datetime(2026, 10, 19, 10, tzinfo=UTC)
    ) == timedelta(hours=16)


def test_span_inside_a_weekend_is_zero() -> None:
    assert WEEKDAYS.elapsed(
        datetime(2026, 10, 17, 9, tzinfo=UTC), datetime(2026, 10, 18, 20, tzinfo=UTC)
    ) == timedelta(0)


def test_weekday_only_span_is_unchanged() -> None:
    a, b = datetime(2026, 10, 19, 9, tzinfo=UTC), datetime(2026, 10, 21, 17, tzinfo=UTC)
    assert WEEKDAYS.elapsed(a, b) == b - a


def test_whole_weeks_are_counted_without_iterating() -> None:
    a = datetime(2026, 1, 5, tzinfo=UTC)  # Monday
    assert WEEKDAYS.elapsed(a, a + timedelta(weeks=52)) == timedelta(days=52 * 5)


def test_weekend_follows_the_rules_timezone() -> None:
    sp = WorkCalendar(frozenset({1, 2, 3, 4, 5}), "America/Sao_Paulo")
    # Sat 01:00 UTC == Fri 22:00 in São Paulo: still a working day there.
    a, b = datetime(2026, 10, 16, 23, tzinfo=UTC), datetime(2026, 10, 17, 1, tzinfo=UTC)
    assert sp.elapsed(a, b) == timedelta(hours=2)
    assert WEEKDAYS.elapsed(a, b) == timedelta(hours=1)


def test_end_before_start_is_not_clamped() -> None:
    a, b = datetime(2026, 10, 19, tzinfo=UTC), datetime(2026, 10, 18, tzinfo=UTC)
    assert WEEKDAYS.elapsed(a, b) == b - a  # preserves today's behavior on bad data


def test_a_span_across_two_weekends_counts_eight_days() -> None:
    assert WEEKDAYS.elapsed(
        datetime(2026, 10, 15, tzinfo=UTC), datetime(2026, 10, 27, tzinfo=UTC)
    ) == timedelta(days=8)


def test_a_span_starting_on_the_weekend_counts_from_monday() -> None:
    assert WEEKDAYS.elapsed(
        datetime(2026, 10, 17, 9, tzinfo=UTC), datetime(2026, 10, 19, 10, tzinfo=UTC)
    ) == timedelta(hours=10)


def test_a_span_crossing_midnight_into_the_local_weekend_stops_at_midnight() -> None:
    sp = WorkCalendar(frozenset({1, 2, 3, 4, 5}), "America/Sao_Paulo")
    # Fri 22:00 -> Sat 02:00 in São Paulo: only the Friday part counts.
    a, b = datetime(2026, 10, 17, 1, tzinfo=UTC), datetime(2026, 10, 17, 5, tzinfo=UTC)
    assert sp.elapsed(a, b) == timedelta(hours=2)


def test_an_interior_holiday_is_skipped() -> None:
    cal = WorkCalendar(frozenset({1, 2, 3, 4, 5}), holidays=(date(2026, 10, 19),))
    # Thu 12:00 -> Tue 12:00: Thu 12h + Fri 24h + (Sat, Sun, Mon off) + Tue 12h
    assert cal.elapsed(
        datetime(2026, 10, 15, 12, tzinfo=UTC), datetime(2026, 10, 20, 12, tzinfo=UTC)
    ) == timedelta(days=2)


def test_a_span_starting_on_a_holiday_skips_it() -> None:
    cal = WorkCalendar(frozenset({1, 2, 3, 4, 5}), holidays=(date(2026, 10, 19),))
    assert cal.elapsed(
        datetime(2026, 10, 19, 9, tzinfo=UTC), datetime(2026, 10, 20, 9, tzinfo=UTC)
    ) == timedelta(hours=9)


def test_a_holiday_on_a_weekend_is_not_subtracted_twice() -> None:
    cal = WorkCalendar(frozenset({1, 2, 3, 4, 5}), holidays=(date(2026, 10, 17),))
    assert cal.elapsed(
        datetime(2026, 10, 16, 12, tzinfo=UTC), datetime(2026, 10, 19, 12, tzinfo=UTC)
    ) == timedelta(days=1)


def test_holidays_apply_on_a_seven_day_calendar() -> None:
    cal = WorkCalendar(frozenset(range(1, 8)), holidays=(date(2026, 10, 17),))
    assert cal.elapsed(
        datetime(2026, 10, 16, 12, tzinfo=UTC), datetime(2026, 10, 19, 12, tzinfo=UTC)
    ) == timedelta(days=2)


def test_holidays_follow_the_calendar_timezone() -> None:
    cal = WorkCalendar(
        frozenset({1, 2, 3, 4, 5}), "America/Sao_Paulo", holidays=(date(2026, 10, 19),)
    )
    # Mon 02:00 UTC == Sun 23:00 SP (already off); Mon 05:00 UTC == Mon 02:00 SP (holiday)
    assert cal.elapsed(
        datetime(2026, 10, 19, 2, tzinfo=UTC), datetime(2026, 10, 19, 5, tzinfo=UTC)
    ) == timedelta(0)


def test_holidays_are_counted_by_range_not_scan() -> None:
    # The first 500 weekdays from Mon 2026-01-05 are holidays, so a 52-week
    # span from that Monday has no working time left.
    holidays = tuple(
        day
        for day in (date(2026, 1, 5) + timedelta(days=i) for i in range(800))
        if day.isoweekday() <= 5
    )[:500]
    cal = WorkCalendar(frozenset({1, 2, 3, 4, 5}), holidays=holidays)
    start = datetime(2026, 1, 5, tzinfo=UTC)
    assert cal.elapsed(start, start + timedelta(weeks=52)) == timedelta(0)
