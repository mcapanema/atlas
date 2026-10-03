/**
 * One executive-dashboard row per team, joined from four index-aligned
 * per-team query arrays. Pure — no React, so the join is testable alone.
 */

import type { UseQueryResult } from "@tanstack/react-query";

import type { DeliveryHealth, FlowMetrics } from "../api/metrics";
import type { ForecastAccuracy, MetricSnapshot } from "../api/snapshots";
import type { Team } from "../api/teams";
import { computeDelta, leadTimePulse, pickBaseline, type Delta, type Pulse } from "./deltas";

/**
 * Three honest cell states: a skeleton means "still asking", "unavailable"
 * means "asked and failed", and "—" is reserved for "asked, answered, and
 * there is genuinely no data". A failed query being retried reads as
 * loading again, so the Retry button gives visible feedback.
 */
export type CellState = "pending" | "failed" | "ready";

export interface TeamRow {
  key: string;
  team: Team;
  metrics: FlowMetrics | undefined;
  accuracy: ForecastAccuracy | undefined;
  health: DeliveryHealth | undefined;
  metricsState: CellState;
  accuracyState: CellState;
  healthState: CellState;
  throughputDelta: Delta | null;
  leadDelta: Delta | null;
  pulse: Pulse | null;
}

/** Per-team query results, each array index-aligned with the team list. */
export interface TeamQueries {
  metrics: UseQueryResult<FlowMetrics>[];
  accuracy: UseQueryResult<ForecastAccuracy>[];
  health: UseQueryResult<DeliveryHealth>[];
  snapshots: UseQueryResult<MetricSnapshot[]>[];
}

function queryState(
  query: { isPending: boolean; isError: boolean; isFetching: boolean } | undefined,
): CellState {
  if (!query || query.isPending) return "pending";
  if (query.isError) return query.isFetching ? "pending" : "failed";
  return "ready";
}

/** Throughput/lead-time deltas vs ~30 days ago, plus the lead-time pulse. */
function trends(
  metrics: FlowMetrics | undefined,
  snapshots: MetricSnapshot[],
  deltasEnabled: boolean,
): Pick<TeamRow, "throughputDelta" | "leadDelta" | "pulse"> {
  if (!metrics) return { throughputDelta: null, leadDelta: null, pulse: null };
  const asOf = metrics.window_end;
  const baseline = deltasEnabled ? pickBaseline(snapshots, asOf, 30) : null;
  return {
    throughputDelta: baseline
      ? computeDelta(metrics.completed, baseline.completed, false, baseline.captured_on)
      : null,
    leadDelta: baseline
      ? computeDelta(
          metrics.lead_time?.p85_seconds,
          baseline.lead_time_p85_seconds,
          true,
          baseline.captured_on,
        )
      : null,
    pulse: leadTimePulse(snapshots, asOf),
  };
}

export function buildTeamRows(
  teams: Team[],
  queries: TeamQueries,
  deltasEnabled: boolean,
): TeamRow[] {
  return teams.map((team, index) => {
    const metrics = queries.metrics[index]?.data;
    return {
      key: team.id,
      team,
      metrics,
      accuracy: queries.accuracy[index]?.data,
      health: queries.health[index]?.data,
      metricsState: queryState(queries.metrics[index]),
      accuracyState: queryState(queries.accuracy[index]),
      healthState: queryState(queries.health[index]),
      ...trends(metrics, queries.snapshots[index]?.data ?? [], deltasEnabled),
    };
  });
}
