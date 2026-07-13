import { useQuery } from "@tanstack/react-query";

import { apiFetch } from "./client";
import { scopeParam, type MetricsScope } from "./metrics";

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

export function useAdvice(scope: MetricsScope, persona: Persona) {
  const param = scopeParam(scope);
  return useQuery({
    queryKey: ["advisor", "advice", scope, persona],
    // Expensive LLM call — never auto-fetch; the page triggers refetch() explicitly.
    enabled: false,
    staleTime: Infinity,
    queryFn: () =>
      apiFetch<DeliveryAdvice>(`/api/recommendations?${param}&persona=${persona}`),
  });
}
