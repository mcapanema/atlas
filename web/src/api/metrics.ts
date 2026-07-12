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
  weeks: ThroughputBucket[];
}

export type MetricsScope = { teamId?: string; projectId?: string };

export function scopeParam(scope: MetricsScope): string | null {
  if (scope.teamId) return `team_id=${scope.teamId}`;
  if (scope.projectId) return `project_id=${scope.projectId}`;
  return null;
}

export function useFlowMetrics(scope: MetricsScope) {
  const param = scopeParam(scope);
  return useQuery({
    queryKey: ["metrics", "flow", scope],
    enabled: param !== null,
    queryFn: () => apiFetch<FlowMetrics>(`/api/metrics?${param}`),
  });
}

export function useFlowHistory(scope: MetricsScope) {
  const param = scopeParam(scope);
  return useQuery({
    queryKey: ["metrics", "history", scope],
    enabled: param !== null,
    queryFn: () => apiFetch<FlowHistory>(`/api/metrics/history?${param}`),
  });
}

export function useAllTeamsFlowMetrics(teams: Team[]) {
  return useQueries({
    queries: teams.map((team) => ({
      queryKey: ["metrics", "flow", { teamId: team.id }],
      queryFn: () => apiFetch<FlowMetrics>(`/api/metrics?team_id=${team.id}`),
    })),
  });
}

export interface LeadTimeDistribution {
  window_start: string;
  window_end: string;
  bins: DurationBin[];
}

export function useLeadTimeDistribution(scope: MetricsScope) {
  const param = scopeParam(scope);
  return useQuery({
    queryKey: ["metrics", "lead-time-distribution", scope],
    enabled: param !== null,
    queryFn: () =>
      apiFetch<LeadTimeDistribution>(`/api/metrics/lead-time-distribution?${param}`),
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

export function useAgingWip(scope: MetricsScope) {
  const param = scopeParam(scope);
  return useQuery({
    queryKey: ["metrics", "aging-wip", scope],
    enabled: param !== null,
    queryFn: () => apiFetch<AgingWip>(`/api/metrics/aging-wip?${param}`),
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

export function useDeliveryHealth(scope: MetricsScope) {
  const param = scopeParam(scope);
  return useQuery({
    queryKey: ["metrics", "health", scope],
    enabled: param !== null,
    queryFn: () => apiFetch<DeliveryHealth>(`/api/metrics/health?${param}`),
  });
}

export function useAllTeamsHealth(teams: Team[]) {
  return useQueries({
    queries: teams.map((team) => ({
      queryKey: ["metrics", "health", { teamId: team.id }],
      queryFn: () => apiFetch<DeliveryHealth>(`/api/metrics/health?team_id=${team.id}`),
    })),
  });
}
