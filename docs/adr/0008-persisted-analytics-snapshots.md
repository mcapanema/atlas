# 8. Persisted analytics snapshots beside compute-on-read

Date: 2026-07-11

## Status

Accepted. Amends ADR-0003 (analytics computed on read).

## Context

Metrics and forecasts are recomputed per request from immutable events
(ADR-0003). That keeps reads correct and storage-free, but three product
needs require remembering what the analytics *said at the time*:
dashboard history (trends of the 30-day metrics themselves), forecast
accuracy (a forecast can only be scored against what actually shipped
after it was made), and future projection improvements that learn from
past snapshots. Recomputation cannot recover a past forecast — it would
use today's history and silently rewrite the prediction.

## Decision

Keep compute-on-read as the live source of truth, and additionally
persist one immutable snapshot pair (flow metrics + Monte Carlo forecast)
per scope (each team, each project) per UTC day. Capture happens inside
the sync request transaction — sync is the only point delivery data
changes — and is idempotent per day. Forecast accuracy is a pure domain
function over past forecast snapshots and actual completion timestamps:
a snapshot resolves once its `remaining` count of completions has landed
after capture; calibration is the share of resolved snapshots whose
actual duration fell within P50/P85.

## Consequences

- Two new tables (`metric_snapshots`, `forecast_snapshots`), tiny by
  construction (scopes × days).
- Live endpoints are unchanged; history and accuracy are additive
  endpoints (`GET /api/metrics/snapshots`, `GET /api/forecasts/accuracy`).
- A day with no sync captures no snapshot — history has gaps if sync
  isn't run daily. Acceptable: snapshots describe observed syncs, and a
  scheduler can be added later without schema changes.
- Snapshot rows are immutable; metric-definition changes only affect rows
  written after the change.
