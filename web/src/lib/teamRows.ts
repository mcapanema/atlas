/**
 * One executive-dashboard row per team, from per-team overview queries
 * index-aligned with the team list. Pure — no React, so the join is
 * testable alone.
 */

import type { UseQueryResult } from "@tanstack/react-query";

import type { DeliveryHealth, FlowMetrics } from "../api/metrics";
import type { ScopeOverview } from "../api/overview";
import type { ForecastAccuracy, MetricSnapshot } from "../api/snapshots";
import type { Team } from "../api/teams";
import { computeDelta, leadTimePulse, pickBaseline, type Delta, type Pulse } from "./deltas";
import { STATS_WINDOW_DAYS } from "./windows";

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
  /** One request feeds the whole row, so every cell shares its state. */
  state: CellState;
  throughputDelta: Delta | null;
  leadDelta: Delta | null;
  pulse: Pulse | null;
}

function queryState(
  query: { isPending: boolean; isError: boolean; isFetching: boolean } | undefined,
): CellState {
  if (!query || query.isPending) return "pending";
  if (query.isError) return query.isFetching ? "pending" : "failed";
  return "ready";
}

/** Throughput/lead-time deltas vs ~STATS_WINDOW_DAYS days ago, plus the lead-time pulse. */
function trends(
  metrics: FlowMetrics | undefined,
  snapshots: MetricSnapshot[],
  deltasEnabled: boolean,
): Pick<TeamRow, "throughputDelta" | "leadDelta" | "pulse"> {
  if (!metrics) return { throughputDelta: null, leadDelta: null, pulse: null };
  const asOf = metrics.window_end;
  const baseline = deltasEnabled ? pickBaseline(snapshots, asOf, STATS_WINDOW_DAYS) : null;
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
  overviews: UseQueryResult<ScopeOverview>[],
  deltasEnabled: boolean,
): TeamRow[] {
  return teams.map((team, index) => {
    const overview = overviews[index];
    const data = overview?.data;
    return {
      key: team.id,
      team,
      metrics: data?.metrics,
      accuracy: data?.accuracy,
      health: data?.health,
      state: queryState(overview),
      ...trends(data?.metrics, data?.snapshots ?? [], deltasEnabled),
    };
  });
}
