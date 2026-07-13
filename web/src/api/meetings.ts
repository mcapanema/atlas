import { useQuery } from "@tanstack/react-query";

import { apiFetch } from "./client";
import { scopeParam, type MetricsScope } from "./metrics";

export type MeetingType = "daily_standup" | "retrospective" | "planning";

export interface TalkingPoint {
  point: string;
  detail: string;
  evidence: string[];
  needs_decision: boolean;
}

export interface MeetingPrep {
  meeting: MeetingType;
  generated_at: string;
  headline: string;
  talking_points: TalkingPoint[];
}

export interface MeetingPrepParams {
  windowDays?: number;
  remaining?: number;
  targetDate?: string; // YYYY-MM-DD
}

export function useMeetingPrep(
  scope: MetricsScope,
  meeting: MeetingType,
  params: MeetingPrepParams = {},
) {
  const search = new URLSearchParams({ meeting });
  if (params.windowDays !== undefined) search.set("window_days", String(params.windowDays));
  if (params.remaining !== undefined) search.set("remaining", String(params.remaining));
  if (params.targetDate) search.set("target_date", params.targetDate);
  const param = scopeParam(scope);
  return useQuery({
    queryKey: ["meetings", "prep", scope, meeting, params],
    // Expensive LLM call — never auto-fetch; the page triggers refetch() explicitly.
    enabled: false,
    staleTime: Infinity,
    queryFn: () =>
      apiFetch<MeetingPrep>(`/api/meetings/prep?${param}&${search.toString()}`),
  });
}
