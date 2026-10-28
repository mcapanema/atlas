import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";

import { apiFetch } from "./client";
import { scopeParam, type MetricsScope } from "./metrics";
import { pollWhileRunning, type RunStatus } from "./runs";

export interface AdvisorStatus {
  configured: boolean;
}

export interface Recommendation {
  title: string;
  priority: "high" | "medium" | "low";
  problem: string;
  root_cause: string;
  action: string;
  evidence: string[];
}

export interface DeliveryAdvice {
  generated_at: string;
  summary: string;
  recommendations: Recommendation[];
}

export function useAdvisorStatus() {
  return useQuery({
    queryKey: ["advisor", "status"],
    queryFn: () => apiFetch<AdvisorStatus>("/api/recommendations/status"),
  });
}

export type Persona =
  | "agile_coach"
  | "engineering_advisor"
  | "project_advisor"
  | "delivery_analyst"
  | "daily_standup"
  | "retrospective"
  | "planning";

export interface AdviceRun {
  id: string;
  status: RunStatus;
  requested_at: string;
  finished_at: string | null;
  error: string | null;
  advice: DeliveryAdvice | null;
}

function adviceRequest(scope: MetricsScope, persona: Persona) {
  return {
    queryKey: ["advisor", "advice", scope, persona],
    path: `/api/recommendations?${scopeParam(scope)}&persona=${persona}`,
  };
}

/** The stored latest run (null when none yet); polled while it is running. */
export function useAdvice(scope: MetricsScope, persona: Persona) {
  const { queryKey, path } = adviceRequest(scope, persona);
  return useQuery({
    queryKey,
    queryFn: () => apiFetch<AdviceRun | null>(path),
    enabled: scopeParam(scope) !== null,
    refetchInterval: pollWhileRunning,
  });
}

/** Starts a run; its answer seeds the `useAdvice` cache so polling begins at once. */
export function useGenerateAdvice(scope: MetricsScope, persona: Persona) {
  const queryClient = useQueryClient();
  const { queryKey, path } = adviceRequest(scope, persona);
  const mutation = useMutation({
    mutationFn: () => apiFetch<AdviceRun>(path, { method: "POST" }),
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
