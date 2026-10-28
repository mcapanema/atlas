import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";

import { apiFetch } from "./client";
import { scopeParam, type MetricsScope } from "./metrics";
import { pollWhileRunning, type RunStatus } from "./runs";

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

export interface MeetingPrepRun {
  id: string;
  status: RunStatus;
  requested_at: string;
  finished_at: string | null;
  error: string | null;
  prep: MeetingPrep | null;
}

function prepRequest(scope: MetricsScope, meeting: MeetingType, params: MeetingPrepParams) {
  const search = new URLSearchParams({ meeting });
  if (params.windowDays !== undefined) search.set("window_days", String(params.windowDays));
  if (params.remaining !== undefined) search.set("remaining", String(params.remaining));
  if (params.targetDate) search.set("target_date", params.targetDate);
  return {
    queryKey: ["meetings", "prep", scope, meeting, params],
    path: `/api/meetings/prep?${scopeParam(scope)}&${search.toString()}`,
  };
}

/** The stored latest run for these params (null when none yet); polled while running. */
export function useMeetingPrep(
  scope: MetricsScope,
  meeting: MeetingType,
  params: MeetingPrepParams = {},
) {
  const { queryKey, path } = prepRequest(scope, meeting, params);
  return useQuery({
    queryKey,
    queryFn: () => apiFetch<MeetingPrepRun | null>(path),
    enabled: scopeParam(scope) !== null,
    refetchInterval: pollWhileRunning,
  });
}

/** Starts a run; its answer seeds the `useMeetingPrep` cache so polling begins at once. */
export function useGenerateMeetingPrep(
  scope: MetricsScope,
  meeting: MeetingType,
  params: MeetingPrepParams = {},
) {
  const queryClient = useQueryClient();
  const { queryKey, path } = prepRequest(scope, meeting, params);
  const mutation = useMutation({
    mutationFn: () => apiFetch<MeetingPrepRun>(path, { method: "POST" }),
    onSuccess: async (run) => {
      // An initial GET still in flight would otherwise overwrite the run with null.
      await queryClient.cancelQueries({ queryKey });
      queryClient.setQueryData(queryKey, run);
    },
  });
  // Mutation state belongs to one request: drop it when the key changes.
  const { reset } = mutation;
  const keyId = JSON.stringify(queryKey);
  useEffect(() => reset, [keyId, reset]);
  return mutation;
}
