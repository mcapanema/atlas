# 3. Analytics are computed on read — no snapshot persistence

Date: 2026-07-11 (backfilled; decided in Phase 3, 2026-07-10)

## Status

Accepted

## Context

Metrics (flow summary, CFD, throughput history, lead-time distribution),
forecasts, and AI advice all derive from the persisted event stream. The
obvious alternative was a snapshot/metric table per computed concept,
populated on sync or by a scheduled job.

At the target scale (thousands of work items, tens of thousands of events
per scope) a full recomputation is milliseconds-to-seconds of pure Python.
Snapshot tables would add: schema + migrations per metric, staleness and
invalidation logic, a write path to keep correct, and a second source of
truth to reconcile against the events.

## Decision

Nothing computed is persisted. Every analytics request recomputes from work
items + events via pure domain functions (`app/domain/metrics/`,
`app/domain/forecasting/`), with inputs assembled once per request by the
shared `ScopeSampleLoader` (`app/application/scope.py`).

## Consequences

- Results are always current; there is no cache-invalidation logic to get wrong.
- The computations are deterministic and trivially unit-testable (the Monte
  Carlo simulation takes a seeded `random.Random`).
- CPU per request grows with event history. Ceilings already paid down:
  single-pass CFD replay, `asyncio.to_thread` around the Monte Carlo loop,
  batched and bounded event loads. If scale outgrows this, introduce
  snapshot tables then — behind the same service interfaces, so routes and
  the frontend don't change.
