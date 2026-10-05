# 13. Sync can rebuild source-derived events

Date: 2026-10-05

## Status

Accepted. Amends ADR-0004 (events are insert-only) and complements
ADR-0009 (pruning).

## Context

Events are insert-only, keyed by deterministic external ids: a re-sync
never changes a stored event. So a connector-mapping fix (a new derived
event, a corrected type) never reaches events an older mapping stored —
the only remedy was deleting the database and re-syncing, which also
destroys user-owned state: advice feedback, persona guidance, metric-rule
overrides, and forecast snapshot history.

## Decision

`POST /api/connectors/linear/sync` with `"rebuild": true` runs the normal
sync, but first deletes the source-derived events (those with an
`external_id`) of every stored item the source returned this run; the
sync loop then re-inserts them from the current mapping in the same
transaction. Events recorded through the events API (no `external_id`)
survive. Items the run didn't return are left to ADR-0009's pruning. The
route then queues the existing history recompute for the organization, so
snapshot history matches the rebuilt events. `SyncSummary.rebuilt` counts
the rebuilt items.

## Consequences

- A mapping fix ships with "run one rebuild sync", not a database wipe;
  user-owned tables are untouched.
- A rebuild rewrites every returned item's events: as slow as a first
  sync, and it holds the recompute runner paused (rule saves wait) until
  it commits.
- A rebuild re-inserts only what the connector fetches now: Linear history is capped at HISTORY_PAGE_SIZE (250) entries per issue, so on an issue with a longer history the events older than that window — kept by insert-only syncs — are deleted by a rebuild (map_issue already warns when the cap is hit). Paginate history per issue if that ever matters.
- An event recorded through the events API *with* an `external_id` on a
  synced item is treated as source-derived and is deleted by a rebuild —
  the same caveat ADR-0009 records for pruning; ADR-0004's planned
  `source` column is the real fix.
