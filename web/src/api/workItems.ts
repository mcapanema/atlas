import { useQuery } from "@tanstack/react-query";

import { apiFetch } from "./client";

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

export function useWorkItems(teamId?: string) {
  return useQuery({
    queryKey: ["work-items", teamId ?? "all"],
    queryFn: () =>
      apiFetch<WorkItem[]>(teamId ? `/api/work-items?team_id=${teamId}` : "/api/work-items"),
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
