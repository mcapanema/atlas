import { useQueries } from "@tanstack/react-query";

import { apiFetch } from "./client";
import {
  metricsParams,
  type DeliveryHealth,
  type FlowMetrics,
  type MetricsFilters,
} from "./metrics";
import type { ForecastAccuracy, MetricSnapshot } from "./snapshots";
import type { Team } from "./teams";

/** One scope's dashboard row, computed server-side from a single scope load. */
export interface ScopeOverview {
  metrics: FlowMetrics;
  health: DeliveryHealth;
  accuracy: ForecastAccuracy;
  snapshots: MetricSnapshot[];
}

export function useAllTeamsOverviews(teams: Team[], filters: MetricsFilters = {}) {
  return useQueries({
    queries: teams.map((team) => ({
      queryKey: ["metrics", "overview", { teamId: team.id }, filters],
      queryFn: () =>
        apiFetch<ScopeOverview>(
          `/api/metrics/overview?${metricsParams({ teamId: team.id }, filters)}`,
        ),
    })),
  });
}
