# 9. Sync prunes work items gone from the source

Date: 2026-10-03

## Status

Accepted. Amends ADR-0004 (idempotent sync by external_id).

## Context

Sync only ever inserted or updated. Issues deleted or trashed in Linear
stayed in Atlas forever: the 2026-10-03 audit found 151 such ghosts, about
100 phantom items in forecast remaining and 17 in WIP. Synced items are
mirrors of the source; the only data on them that isn't re-derivable is
events recorded through the events API, which are rare and meaningless once
the upstream item is gone. Keeping ghosts buys no audit trail, only wrong
numbers.

## Decision

After a full fetch, `SyncService` deletes every synced work item (and its
events) whose `external_id` the source didn't return. The prune is scoped to
teams that returned at least one live item that run, so credentials that
lost a team's access, or an empty fetch, delete nothing. Items without an
`external_id` (events API, demo data) are never touched. `SyncSummary`
reports the count as `deleted`.

## Consequences

- Metrics stop counting work that no longer exists upstream.
- Events are no longer strictly append-only: a pruned item's events go with
  it. Persisted snapshots (ADR-0008) keep what they said at the time.
- A node the connector skips as malformed is pruned and recreated by the
  next clean sync.
- A team whose every issue was deleted upstream keeps its items.
- Events recorded through the events API on a pruned item are deleted with
  it and cannot be recovered.
