import { useQueries, useQuery } from "@tanstack/react-query";

import type { DailyFlowCount, DurationBin, ThroughputBucket } from "../lib/charts";
import { apiFetch } from "./client";
import type { Team } from "./teams";

export type { DailyFlowCount, DurationBin, ThroughputBucket };

export interface DurationStats {
  p50_seconds: number;
  p75_seconds: number;
  p85_seconds: number;
  p95_seconds: number;
  mean_seconds: number;
}

export interface FlowMetrics {
  window_start: string;
  window_end: string;
  completed: number;
  wip: number;
  lead_time: DurationStats | null;
  cycle_time: DurationStats | null;
  blocked_seconds: number;
  flow_efficiency: number | null;
  queue_time: DurationStats | null;
  touch_time: DurationStats | null;
}

export interface FlowHistory {
  window_start: string;
  window_end: string;
  days: DailyFlowCount[];
  buckets: ThroughputBucket[];
  bucket_days: number;
  data_as_of: string | null;
}

export type MetricsScope = { teamId?: string; projectId?: string };

export function scopeParam(scope: MetricsScope): string | null {
  if (scope.teamId) return `team_id=${scope.teamId}`;
  if (scope.projectId) return `project_id=${scope.projectId}`;
  return null;
}

export interface MetricsFilters {
  windowDays?: number;
  start?: string; // ISO date YYYY-MM-DD, always paired with end
  end?: string;
  types?: string[];
  excludeStates?: string[];
}

export function metricsParams(
  scope: MetricsScope,
  filters: MetricsFilters = {},
): string | null {
  const search = new URLSearchParams();
  if (scope.teamId) search.set("team_id", scope.teamId);
  else if (scope.projectId) search.set("project_id", scope.projectId);
  else return null;
  if (filters.start && filters.end) {
    search.set("start", filters.start);
    search.set("end", filters.end);
  } else if (filters.windowDays !== undefined) {
    search.set("window_days", String(filters.windowDays));
  }
  for (const type of filters.types ?? []) search.append("types", type);
  for (const state of filters.excludeStates ?? []) search.append("exclude_states", state);
  return search.toString();
}

export function useFlowMetrics(scope: MetricsScope, filters: MetricsFilters = {}) {
  const params = metricsParams(scope, filters);
  return useQuery({
    queryKey: ["metrics", "flow", scope, filters],
    enabled: params !== null,
    queryFn: () => apiFetch<FlowMetrics>(`/api/metrics?${params}`),
  });
}

export function useFlowHistory(scope: MetricsScope, filters: MetricsFilters = {}) {
  const params = metricsParams(scope, filters);
  return useQuery({
    queryKey: ["metrics", "history", scope, filters],
    enabled: params !== null,
    queryFn: () => apiFetch<FlowHistory>(`/api/metrics/history?${params}`),
  });
}

export function useAllTeamsFlowMetrics(teams: Team[], filters: MetricsFilters = {}) {
  return useQueries({
    queries: teams.map((team) => ({
      queryKey: ["metrics", "flow", { teamId: team.id }, filters],
      queryFn: () =>
        apiFetch<FlowMetrics>(`/api/metrics?${metricsParams({ teamId: team.id }, filters)}`),
    })),
  });
}

export interface LeadTimeDistribution {
  window_start: string;
  window_end: string;
  bins: DurationBin[];
}

export function useLeadTimeDistribution(scope: MetricsScope, filters: MetricsFilters = {}) {
  const params = metricsParams(scope, filters);
  return useQuery({
    queryKey: ["metrics", "lead-time-distribution", scope, filters],
    enabled: params !== null,
    queryFn: () =>
      apiFetch<LeadTimeDistribution>(`/api/metrics/lead-time-distribution?${params}`),
  });
}

export interface AgingItem {
  work_item_id: string;
  title: string;
  state: string;
  age_seconds: number;
  over_p85: boolean;
}

export interface AgingWip {
  now: string;
  cycle_time_p85_seconds: number | null;
  items: AgingItem[];
}

export function useAgingWip(scope: MetricsScope, filters: MetricsFilters = {}) {
  const params = metricsParams(scope, filters);
  return useQuery({
    queryKey: ["metrics", "aging-wip", scope, filters],
    enabled: params !== null,
    queryFn: () => apiFetch<AgingWip>(`/api/metrics/aging-wip?${params}`),
  });
}

export interface HealthComponent {
  name: string;
  score: number;
  reason: string;
}

export interface DeliveryHealth {
  window_start: string;
  window_end: string;
  score: number | null;
  band: "healthy" | "warning" | "critical" | null;
  components: HealthComponent[];
}

export function useDeliveryHealth(scope: MetricsScope, filters: MetricsFilters = {}) {
  const params = metricsParams(scope, filters);
  return useQuery({
    queryKey: ["metrics", "health", scope, filters],
    enabled: params !== null,
    queryFn: () => apiFetch<DeliveryHealth>(`/api/metrics/health?${params}`),
  });
}

export function useAllTeamsHealth(teams: Team[], filters: MetricsFilters = {}) {
  return useQueries({
    queries: teams.map((team) => ({
      queryKey: ["metrics", "health", { teamId: team.id }, filters],
      queryFn: () =>
        apiFetch<DeliveryHealth>(`/api/metrics/health?${metricsParams({ teamId: team.id }, filters)}`),
    })),
  });
}
