import { useQuery } from "@tanstack/react-query";

import type { BugBucket, DailyFlowCount, DurationBin, ThroughputBucket } from "../lib/charts";
import { apiFetch } from "./client";

export type { BugBucket, DailyFlowCount, DurationBin, ThroughputBucket };

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

export function metricsParams(scope: MetricsScope, filters: MetricsFilters = {}): string | null {
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

export interface LeadTimeDistribution {
  window_start: string;
  window_end: string;
  bins: DurationBin[];
  /** Exact lead-time percentiles over the window; null when nothing completed. */
  p50_seconds: number | null;
  p85_seconds: number | null;
}

export function useLeadTimeDistribution(scope: MetricsScope, filters: MetricsFilters = {}) {
  const params = metricsParams(scope, filters);
  return useQuery({
    queryKey: ["metrics", "lead-time-distribution", scope, filters],
    enabled: params !== null,
    queryFn: () => apiFetch<LeadTimeDistribution>(`/api/metrics/lead-time-distribution?${params}`),
  });
}

export interface AgingItem {
  work_item_id: string;
  title: string;
  state: string;
  age_seconds: number;
  over_percentile: boolean;
  /** Who the item is assigned to as of the last sync; null when unassigned. */
  assignee: string | null;
  /** A blocked period is open right now, under the team's metric rules. */
  blocked: boolean;
  /** Past the median (P50) cycle time of the aging history. */
  over_median: boolean;
  /** The work-item type under the team's type rules, e.g. "bug". */
  type: string;
}

export interface AgingWip {
  now: string;
  cycle_time_percentile_seconds: number | null;
  cycle_time_median_seconds: number | null;
  items: AgingItem[];
  percentile: number;
  history_days: number;
}

export function useAgingWip(scope: MetricsScope, filters: MetricsFilters = {}) {
  const params = metricsParams(scope, filters);
  return useQuery({
    queryKey: ["metrics", "aging-wip", scope, filters],
    enabled: params !== null,
    queryFn: () => apiFetch<AgingWip>(`/api/metrics/aging-wip?${params}`),
  });
}

/** In-cycle time items completed in the window spent in one workflow state. */
export interface StateTime {
  state: string;
  total_seconds: number;
  /** total over every state's total, 0–1. */
  share: number;
  median_seconds: number;
  items: number;
  /** Items in progress in this state at the window's end. */
  queue: number;
  wait_state: boolean;
  /** The row's team in a project that spans teams; null otherwise. */
  team: string | null;
}

export interface StateTimes {
  window_start: string;
  window_end: string;
  measured: number;
  min_sample: number;
  /** Most total time first. */
  states: StateTime[];
  /** The state with the most total time; null below min_sample measured items. */
  bottleneck: string | null;
  /** The bottleneck row's team; null when the scope isn't split by team. */
  bottleneck_team: string | null;
}

export function useStateTimes(scope: MetricsScope, filters: MetricsFilters = {}) {
  const params = metricsParams(scope, filters);
  return useQuery({
    queryKey: ["metrics", "state-times", scope, filters],
    enabled: params !== null,
    queryFn: () => apiFetch<StateTimes>(`/api/metrics/state-times?${params}`),
  });
}

export interface HealthComponent {
  name: string;
  score: number;
  /** The score read against the scope's cutoffs, like the overall band. */
  band: "healthy" | "warning" | "critical";
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

export type DoraBand = "elite" | "high" | "medium" | "low";

/** DORA's four keys for one team; a null band means too few samples to rate. */
export interface DoraMetrics {
  window_start: string;
  window_end: string;
  /** Repositories mapped to the team; 0 means nothing can be measured. */
  codebases: number;
  min_sample: number;
  deployments: number;
  deploys_per_week: number;
  deploy_frequency_band: DoraBand | null;
  lead_time_median_seconds: number | null;
  lead_time_changes: number;
  lead_time_band: DoraBand | null;
  change_failure_rate: number | null;
  failed_deployments: number;
  finished_deployments: number;
  change_failure_band: DoraBand | null;
  restore_median_seconds: number | null;
  restores: number;
  restore_band: DoraBand | null;
}

/** Team scope only: a project answers 422, so no team means no request. */
export function useDora(teamId: string | undefined, filters: MetricsFilters = {}) {
  const params = teamId
    ? metricsParams(
        { teamId },
        { windowDays: filters.windowDays, start: filters.start, end: filters.end },
      )
    : null;
  return useQuery({
    queryKey: ["metrics", "dora", teamId, filters],
    enabled: params !== null,
    queryFn: () => apiFetch<DoraMetrics>(`/api/metrics/dora?${params}`),
  });
}

/** Bugs fixed in the window (median lead time) and open at its end. */
export interface FixStats {
  fixed: number;
  /** Null only when nothing was fixed. */
  median_seconds: number | null;
  open: number;
  oldest_open_seconds: number | null;
}

export interface PriorityFix extends FixStats {
  priority: "urgent" | "high" | "medium" | "low" | "none";
}

/** The Bugs section (ADR-0030); no_mapping and no_matches carry zeros and empty lists. */
export interface BugMetrics {
  state: "ok" | "no_mapping" | "no_matches";
  /** The labels that map to the bug type, as stored. */
  bug_labels: string[];
  window_start: string;
  window_end: string;
  bucket_days: number;
  buckets: BugBucket[];
  created: number;
  completed: number;
  non_bug_completed: number;
  all_completed: number;
  /** New bugs per non-bug item completed; null when no non-bug item completed. */
  per_item: number | null;
  /** Bugs completed over all items completed; null when nothing completed. */
  share: number | null;
  min_sample: number;
  all_bugs: FixStats;
  /** Urgent, high, medium, low, none — always five rows in the ok state. */
  priorities: PriorityFix[];
  /** Bugs in the All bugs row whose priority is unknown. */
  unknown_priority: number;
  data_as_of: string | null;
}

/** Team scope only. The type filter never applies: it would remove one side of each ratio. */
export function useBugMetrics(teamId: string | undefined, filters: MetricsFilters = {}) {
  const params = { ...filters, types: undefined };
  const search = teamId ? metricsParams({ teamId }, params) : null;
  return useQuery({
    queryKey: ["metrics", "bugs", teamId, params],
    enabled: search !== null,
    queryFn: () => apiFetch<BugMetrics>(`/api/metrics/bugs?${search}`),
  });
}
