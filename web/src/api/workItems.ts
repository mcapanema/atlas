import { useQuery } from "@tanstack/react-query";

import { apiFetch } from "./client";
import type { MetricsScope } from "./metrics";

export interface WorkItem {
  id: string;
  team_id: string;
  project_id: string | null;
  title: string;
  type: string;
  state: string;
  external_id: string | null;
  created_at: string;
}

export interface StatePeriod {
  state: string;
  entered_at: string;
  exited_at: string | null;
}

export interface BlockedPeriod {
  started_at: string;
  ended_at: string | null;
}

export interface WorkItemTimeline {
  state_periods: StatePeriod[];
  blocked_periods: BlockedPeriod[];
}

export interface PagedWorkItems {
  items: WorkItem[];
  total: number;
}

export const WORK_ITEMS_PAGE_SIZE = 50;

export function useWorkItems(teamId?: string, page = 1) {
  const params = new URLSearchParams({
    limit: String(WORK_ITEMS_PAGE_SIZE),
    offset: String((page - 1) * WORK_ITEMS_PAGE_SIZE),
  });
  if (teamId) params.set("team_id", teamId);
  return useQuery({
    queryKey: ["work-items", teamId ?? "all", page],
    queryFn: () => apiFetch<PagedWorkItems>(`/api/work-items?${params.toString()}`),
  });
}

export function useWorkItem(id: string) {
  return useQuery({
    queryKey: ["work-items", "detail", id],
    queryFn: () => apiFetch<WorkItem>(`/api/work-items/${id}`),
  });
}

export function useWorkItemTimeline(id: string) {
  return useQuery({
    queryKey: ["work-items", "timeline", id],
    queryFn: () => apiFetch<WorkItemTimeline>(`/api/work-items/${id}/timeline`),
  });
}

/** Distinct states present in a scope — options for the exclude-states filter. */
export function useWorkItemStates(scope: MetricsScope = {}) {
  const params = new URLSearchParams();
  if (scope.teamId) params.set("team_id", scope.teamId);
  else if (scope.projectId) params.set("project_id", scope.projectId);
  const query = params.toString();
  return useQuery({
    queryKey: ["work-items", "states", scope],
    queryFn: () => apiFetch<string[]>(`/api/work-items/states${query ? `?${query}` : ""}`),
  });
}
