import { useQuery } from "@tanstack/react-query";

import type { OutcomeBucket } from "../lib/charts";
import { apiFetch } from "./client";
import { scopeParam, type MetricsScope } from "./metrics";

export type { OutcomeBucket };

export interface CompletionForecast {
  trials: number;
  p50_date: string;
  p75_date: string;
  p85_date: string;
  p95_date: string;
  outcomes: OutcomeBucket[];
}

export interface Forecast {
  window_start: string;
  window_end: string;
  remaining: number;
  completion: CompletionForecast | null;
  confidence: number | null;
}

export function useForecast(scope: MetricsScope, targetDate?: string) {
  const param = scopeParam(scope);
  const target = targetDate ? `&target_date=${targetDate}` : "";
  return useQuery({
    queryKey: ["forecasts", scope, targetDate ?? null],
    enabled: param !== null,
    queryFn: () => apiFetch<Forecast>(`/api/forecasts?${param}${target}`),
  });
}
