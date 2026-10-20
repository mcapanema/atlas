"""The working calendar a team's duration metrics are measured on."""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

_ALL_DAYS = frozenset(range(1, 8))


@dataclass(frozen=True)
class WorkCalendar:
    """Which ISO weekdays (1 = Monday ... 7 = Sunday) count as working, on a time zone's calendar.

    ponytail: a local day counts as 24 h, so a DST-change day is off by an
    hour, and holidays aren't modelled. Upgrade path: a `holidays:
    tuple[date, ...]` rule that subtracts like a non-working weekday.
    """

    working_days: frozenset[int]
    timezone: str = "UTC"

    def elapsed(self, start: datetime, end: datetime) -> timedelta:
        """Time from `start` to `end` with non-working local days removed.

        An end at or before the start is plain `end - start`, unclamped.
        """
        if end <= start or self.working_days >= _ALL_DAYS:
            return end - start
        tz = ZoneInfo(self.timezone)
        local_start, local_end = start.astimezone(tz), end.astimezone(tz)
        first, last = local_start.date(), local_end.date()
        off = self._overlap(first, local_start, local_end)
        if last != first:
            off += self._overlap(last, local_start, local_end)
        interior = max(0, (last - first).days - 1)
        weeks, rest = divmod(interior, 7)
        off_days = weeks * (7 - len(self.working_days)) + sum(
            1
            for i in range(rest)
            if (first + timedelta(days=1 + i)).isoweekday() not in self.working_days
        )
        return max(timedelta(0), (end - start) - off - timedelta(days=off_days))

    def _overlap(self, day: date, a: datetime, b: datetime) -> timedelta:
        """Length of [a, b] inside `day` when `day` is non-working, else zero."""
        if day.isoweekday() in self.working_days:
            return timedelta(0)
        begin = datetime.combine(day, time(), tzinfo=a.tzinfo)
        return max(timedelta(0), min(b, begin + timedelta(days=1)) - max(a, begin))


EVERY_DAY = WorkCalendar(_ALL_DAYS)
