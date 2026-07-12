import { useQueries, useQuery } from "@tanstack/react-query";

import { apiFetch } from "./client";
import { scopeParam, type MetricsScope } from "./metrics";
import type { Team } from "./teams";

export interface MetricSnapshot {
  captured_on: string;
  window_days: number;
  completed: number;
  wip: number;
  lead_time_p50_seconds: number | null;
  lead_time_p85_seconds: number | null;
  cycle_time_p50_seconds: number | null;
  cycle_time_p85_seconds: number | null;
  blocked_seconds: number;
  flow_efficiency: number | null;
}

export interface ForecastAccuracy {
  evaluated: number;
  pending: number;
  p50_hit_rate: number | null;
  p85_hit_rate: number | null;
  mean_abs_error_days: number | null;
}

export function useMetricSnapshots(scope: MetricsScope) {
  const param = scopeParam(scope);
  return useQuery({
    queryKey: ["metrics", "snapshots", scope],
    enabled: param !== null,
    queryFn: () => apiFetch<MetricSnapshot[]>(`/api/metrics/snapshots?${param}`),
  });
}

export function useForecastAccuracy(scope: MetricsScope) {
  const param = scopeParam(scope);
  return useQuery({
    queryKey: ["forecasts", "accuracy", scope],
    enabled: param !== null,
    queryFn: () => apiFetch<ForecastAccuracy>(`/api/forecasts/accuracy?${param}`),
  });
}

export function useAllTeamsSnapshots(teams: Team[]) {
  return useQueries({
    queries: teams.map((team) => ({
      queryKey: ["metrics", "snapshots", { teamId: team.id }],
      queryFn: () => apiFetch<MetricSnapshot[]>(`/api/metrics/snapshots?team_id=${team.id}`),
    })),
  });
}

export function useAllTeamsForecastAccuracy(teams: Team[]) {
  return useQueries({
    queries: teams.map((team) => ({
      queryKey: ["forecasts", "accuracy", { teamId: team.id }],
      queryFn: () =>
        apiFetch<ForecastAccuracy>(`/api/forecasts/accuracy?team_id=${team.id}`),
    })),
  });
}
