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
