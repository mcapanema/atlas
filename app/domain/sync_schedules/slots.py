"""When an organization's auto sync runs (ADR-0014).

A slot is a wall-clock time in the schedule's zone (window start, then
every interval up to the window end) on a selected weekday, as a UTC
instant. Wall-clock arithmetic means DST moves the UTC instant, not the
local time. A local time that a DST gap skips maps onto an instant that
already exists, and the two collapse into one slot.
"""

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.domain.sync_schedules.entities import MIN_INTERVAL_MINUTES, SyncSchedule

# Today plus a full week either way: any selected weekday recurs within it.
_SEARCH_DAYS = 8
# A manual sync this close before a slot (or any time after it) makes the
# slot redundant; the minimum interval, so skipping costs at most one interval.
MANUAL_SYNC_COVERS = timedelta(minutes=MIN_INTERVAL_MINUTES)


def slots_on(schedule: SyncSchedule, day: date) -> list[datetime]:
    """The sync instants (UTC, ascending) for one local calendar day."""
    if day.isoweekday() not in schedule.days:
        return []
    midnight = datetime(day.year, day.month, day.day, tzinfo=ZoneInfo(schedule.timezone))
    first = _minute_of_day(schedule.window_start)
    last = _minute_of_day(schedule.window_end)
    # Aware + timedelta is wall-clock arithmetic: zoneinfo re-derives the
    # offset for each slot's local time.
    instants = {
        (midnight + timedelta(minutes=minute)).astimezone(UTC)
        for minute in range(first, last + 1, schedule.interval_minutes)
    }
    return sorted(instants)


def latest_slot(schedule: SyncSchedule, now: datetime) -> datetime | None:
    """The last slot at or before `now`, looking back a week."""
    for day in _days_from(schedule, now, step=-1):
        past = [slot for slot in slots_on(schedule, day) if slot <= now]
        if past:
            return past[-1]
    return None


def next_slot(schedule: SyncSchedule, now: datetime) -> datetime | None:
    """The first slot after `now`; None while auto sync is off."""
    if not schedule.enabled:
        return None
    for day in _days_from(schedule, now, step=1):
        upcoming = [
            slot for slot in slots_on(schedule, day) if slot > now and not _covered(schedule, slot)
        ]
        if upcoming:
            return upcoming[0]
    return None


def due_slot(schedule: SyncSchedule, now: datetime) -> datetime | None:
    """The slot to sync for now, if one is pending.

    Only the latest past slot counts, so slots missed while Atlas was off
    collapse into one catch-up run. A slot at or before the last save, one
    already run, or one a manual sync covered is never due.
    """
    if not schedule.enabled:
        return None
    slot = latest_slot(schedule, now)
    if slot is None or slot <= schedule.updated_at:
        return None
    if schedule.last_run is not None and slot <= schedule.last_run.slot_at:
        return None
    return None if _covered(schedule, slot) else slot


def _covered(schedule: SyncSchedule, slot: datetime) -> bool:
    """Whether a manual sync made this slot redundant."""
    manual = schedule.last_manual_sync_at
    return manual is not None and manual >= slot - MANUAL_SYNC_COVERS


def _days_from(schedule: SyncSchedule, now: datetime, *, step: int) -> list[date]:
    today = now.astimezone(ZoneInfo(schedule.timezone)).date()
    return [today + timedelta(days=offset * step) for offset in range(_SEARCH_DAYS + 1)]


def _minute_of_day(moment: time) -> int:
    return moment.hour * 60 + moment.minute
