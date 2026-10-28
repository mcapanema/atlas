# 22. Background sync jobs

Date: 2026-10-28

## Status

Accepted. Amends ADR-0014 (the shared lock moved to `SyncJobRunner`);
builds on ADR-0013 (rebuild).

## Context

A sync held its HTTP request open for the whole Linear fetch, and a second
sync waited on a bare `asyncio.Lock`. That was a deliberate simplification
(a `ponytail:` note at the lock), fine while one connector synced in
seconds. A second connector makes syncs slower: a browser request or an MCP
call would time out while the sync was still working, and a waiting request
gave no hint of what it was waiting for.

## Decision

- **In-process job, status in memory.** `SyncJobRunner`
  (`app/api/sync_jobs.py`) runs one sync as one asyncio task (ADR-0002: no
  queue). A sync is one transaction, so a restart mid-sync leaves no partial
  data and only loses the job record. The last 20 finished jobs are kept in
  memory; a client polling a job lost to a restart gets `404` and shows it
  as interrupted. Marked `ponytail:` with a `sync_runs` table as the upgrade
  path.
- **No queue: covered or 409.** A request while a job runs gets the running
  job back (`202`) when that job covers it: an organization sync covers a
  plain organization sync and any team sync of that organization; a rebuild
  is covered only by a rebuild; a team sync covers only the same team.
  Anything else answers `409` naming the running job's kind and start time.
  Previously the request waited on the lock.
- **Organization bootstrap stays in the request.** `organization_id: null`
  with no organization resolves (and, on first run, creates) it
  synchronously and commits before the job starts: the job is keyed by
  organization id.
- **Coarse phase.** `teams`, `projects`, `work_items`, `snapshots` — no
  per-page progress until a slow fetch proves it is needed.
- **MCP `run_sync` waits up to 45 s**, polling the job every second, then
  returns the outcome. On timeout it returns a still-running message with
  the job's phase ("phase: starting" before the first phase is reported)
  and asks to call `run_sync` again: that call is covered by the running
  job, so it attaches instead of starting another.
- **A rebuild job succeeds when the sync commits.** The snapshot-history
  rewrite it queues keeps reporting through the recompute status (ADR-0013
  unchanged).
- **Routes and status.** Sync routes answer `202` with a `SyncJobRead`;
  `GET /api/connectors/linear/jobs/{job_id}` reads one. `LinearStatusRead`
  carries `running: SyncJobRead | None` (any job, manual or automatic) in
  place of `auto_syncing`. The web polls the job.
- **One lock, every entry point.** Manual routes, the MCP tool and
  `AutoSyncRunner` all run through `SyncJobRunner`, which holds the lock and
  commits inside it, inside `recompute.paused()`.

## Consequences

- No queue: a request the running job does not cover is a `409`; the caller
  retries when it finishes.
- Job history is lost on restart; outcomes before it are not recoverable.
- Atlas must still run as a single uvicorn worker (as ADR-0014): the lock
  and the job registry are per process.
