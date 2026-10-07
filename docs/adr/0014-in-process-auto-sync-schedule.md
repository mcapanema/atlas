# 14. In-process auto-sync schedule

Date: 2026-10-07

## Status

Accepted.

## Context

Sync was manual-only (the Connectors page's "Sync now", or the MCP
`run_sync` tool). The 2026-10-06 Faturamento & Glosa audit found 28 of 31
status mismatches against Linear were just staleness: issues changed after
the last manual sync. Engineering Managers want fresh data during working
hours without remembering to click, but Atlas is a single-deployable
monolith with no queue or cron (ADR-0002).

## Decision

Each organization may have one `SyncSchedule`
(`app/domain/sync_schedules/`): ISO weekdays (1 = Monday … 7 = Sunday), a
window of local wall-clock times (start ≤ end, both included), an interval
(15–1440 minutes), and an IANA timezone. Its slots are window start, then
every interval through window end, on each selected day (`slots.py`).
It's stored in `sync_schedules`, edited through
`GET/PUT /api/organizations/{id}/sync-schedule` and the Connectors page.

An in-process `AutoSyncRunner` (`app/api/auto_sync.py`), one asyncio task
started by the lifespan, ticks every 60 s. A schedule is due when its
latest slot at or before now is later than both its last save
(`updated_at`) and its last run's slot. It runs the same plain sync +
snapshot capture as the manual route, then records the outcome (`last_run`:
slot, finish time, error) on the schedule. Manual and automatic syncs share
one `asyncio.Lock`.

## Consequences

- Missed slots (Atlas off, laptop asleep) collapse into one catch-up sync
  at startup, never a burst.
- Saving a schedule never fires a slot that already passed.
- A failed sync, or an unset `ATLAS_LINEAR_API_KEY`, consumes its slot and
  shows the error on the Connectors page; there's no retry until the next
  slot.
- DST moves the UTC instant, not the local time. A local time a DST gap
  skips merges with the instant it lands on, and a repeated local time
  fires once.
- Overnight windows (22:00–02:00) aren't supported. Use two days' windows
  if that ever matters.
- One scheduler per process: Atlas must run as a single worker. Several
  workers would each sync; a DB lease is the upgrade path.
- Zone data comes from the OS (`python:3.13-slim` ships `tzdata`). Add the
  `tzdata` PyPI package if Atlas ever runs where it's missing.
- Auto sync is always a plain sync. A rebuild (ADR-0013) stays a deliberate,
  manual act.
