import { useQuery } from "@tanstack/react-query";

import { apiFetch } from "./client";

export interface DurationStats {
  p50_seconds: number;
  p75_seconds: number;
  p85_seconds: number;
  p95_seconds: number;
  mean_seconds: number;
}

export interface TeamFlowMetrics {
  window_start: string;
  window_end: string;
  completed: number;
  wip: number;
  lead_time: DurationStats | null;
  cycle_time: DurationStats | null;
  blocked_seconds: number;
  flow_efficiency: number | null;
}

export function useTeamFlowMetrics(teamId?: string) {
  return useQuery({
    queryKey: ["metrics", "flow", teamId],
    enabled: !!teamId,
    queryFn: () => apiFetch<TeamFlowMetrics>(`/api/metrics?team_id=${teamId}`),
  });
}
