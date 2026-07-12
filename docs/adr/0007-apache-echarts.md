# 7. Dashboard charts use Apache ECharts

Date: 2026-07-11 (backfilled; decided in Phase 4, 2026-07-10)

## Status

Accepted

## Context

The dashboards need a stacked-area Cumulative Flow Diagram over daily
buckets, weekly throughput bars, and a lead-time histogram. Candidates:
Recharts (SVG, React-idiomatic), Chart.js, Apache ECharts. The CFD is the
demanding case — months of daily points across several bands, where SVG
node counts get expensive.

## Decision

Apache ECharts (canvas renderer), wrapped exactly once:

- `web/src/components/EChart.tsx` owns the imperative lifecycle
  (init / setOption / resize / dispose).
- Pure option builders live in `web/src/lib/charts.ts`; pages never touch
  the ECharts API directly.
- Imports go through `echarts/core` with explicit module registration, so
  only the chart and component types the builders use ship in the bundle.

## Consequences

- Canvas rendering keeps daily-resolution charts cheap to redraw.
- jsdom has no canvas: page tests mock the `EChart` wrapper; only
  `charts.test.ts` asserts on option contents.
- A new chart type must register its module in `EChart.tsx` — a missing
  registration fails at runtime, not in tests (documented in
  `web/CLAUDE.md`).
