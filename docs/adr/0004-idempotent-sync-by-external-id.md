# 4. Sync upserts idempotently, keyed by external_id

Date: 2026-07-11 (backfilled; decided in Phase 2b, 2026-07-09)

## Status

Accepted

## Context

Connector syncs re-run: manually (the Sync button), after failures, and
eventually on a schedule. A naive re-import would duplicate teams, projects,
work items, and events — silently corrupting every downstream metric, with
no cleanup path.

## Decision

Every synced row stores the source system's identifier in an `external_id`
column. `SyncService` matches on `external_id` and updates instead of
inserting — running the same sync twice is a no-op. Uniqueness is enforced
by the database (unique indexes on all four synced tables), so two
concurrent syncs cannot double-insert: the loser's `IntegrityError`
surfaces as a 409.

`external_id` is deliberately not namespaced by vendor while Linear is the
only connector. Connector #2 requires a `source` column and a composite
unique index first.

## Consequences

- Sync is safe to re-run and safe to race; the schema is the last line of
  defense, not application-level read-before-insert.
- Items renamed or re-parented upstream converge on the next sync.
- A second connector has a known, small migration cost (vendor namespacing)
  before it can ship.
