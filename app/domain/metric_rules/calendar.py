"""The working calendar a team's duration metrics are measured on."""

from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

_ALL_DAYS = frozenset(range(1, 8))


@dataclass(frozen=True)
class WorkCalendar:
    """Which ISO weekdays (1 = Monday ... 7 = Sunday) count as working, on a time zone's calendar.

    `holidays` are whole local days off on top of the non-working weekdays.
    Those landing on a non-working weekday are dropped (already off), and
    the rest are kept sorted and deduplicated.

    ponytail: a local day counts as 24 h, so a DST-change day is off by an
    hour. Upgrade path: measure each local day's real length.
    """

    working_days: frozenset[int]
    timezone: str = "UTC"
    holidays: tuple[date, ...] = ()

    def __post_init__(self) -> None:
        kept = sorted({day for day in self.holidays if day.isoweekday() in self.working_days})
        object.__setattr__(self, "holidays", tuple(kept))

    def elapsed(self, start: datetime, end: datetime) -> timedelta:
        """Time from `start` to `end` with non-working local days removed.

        An end at or before the start is plain `end - start`, unclamped.
        """
        if end <= start or (self.working_days >= _ALL_DAYS and not self.holidays):
            return end - start
        tz = ZoneInfo(self.timezone)
        local_start, local_end = start.astimezone(tz), end.astimezone(tz)
        first, last = local_start.date(), local_end.date()
        off = self._overlap(first, local_start, local_end)
        if last != first:
            off += self._overlap(last, local_start, local_end)
        interior = max(0, (last - first).days - 1)
        weeks, rest = divmod(interior, 7)
        off_days = (
            weeks * (7 - len(self.working_days))
            + sum(
                1
                for i in range(rest)
                if (first + timedelta(days=1 + i)).isoweekday() not in self.working_days
            )
            + bisect_left(self.holidays, last)
            - bisect_right(self.holidays, first)
        )
        return max(timedelta(0), (end - start) - off - timedelta(days=off_days))

    def _is_off(self, day: date) -> bool:
        if day.isoweekday() not in self.working_days:
            return True
        index = bisect_left(self.holidays, day)
        return index < len(self.holidays) and self.holidays[index] == day

    def _overlap(self, day: date, a: datetime, b: datetime) -> timedelta:
        """Length of [a, b] inside `day` when `day` is off, else zero."""
        if not self._is_off(day):
            return timedelta(0)
        begin = datetime.combine(day, time(), tzinfo=a.tzinfo)
        return max(timedelta(0), min(b, begin + timedelta(days=1)) - max(a, begin))


EVERY_DAY = WorkCalendar(_ALL_DAYS)
