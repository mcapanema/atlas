import { useQuery } from "@tanstack/react-query";

import type { OutcomeBucket } from "../lib/charts";
import { apiFetch } from "./client";
import { metricsParams, type MetricsFilters, type MetricsScope } from "./metrics";

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

export interface ForecastOptions {
  /** Only the item filters are forwarded — see the comment below. */
  filters?: MetricsFilters;
  /** ISO YYYY-MM-DD; asks the API for the odds of finishing by this date. */
  targetDate?: string;
  /** Scenario override for the backlog size; omitted means "the real count". */
  remaining?: number;
}

export function useForecast(scope: MetricsScope, options: ForecastOptions = {}) {
  const { filters, targetDate, remaining } = options;
  // The page's period is deliberately NOT forwarded: window_end doubles as the
  // forecast origin, so a custom past range would turn "P85 finish" into a
  // backtest date instead of a prediction. Passing only the item-filter subset
  // to metricsParams makes that structural rather than a rule to remember.
  const params = metricsParams(scope, {
    types: filters?.types,
    excludeStates: filters?.excludeStates,
  });
  const search = new URLSearchParams(params ?? "");
  if (targetDate) search.set("target_date", targetDate);
  if (remaining !== undefined) search.set("remaining", String(remaining));
  return useQuery({
    queryKey: ["forecasts", scope, filters?.types, filters?.excludeStates, targetDate ?? null, remaining ?? null],
    enabled: params !== null,
    queryFn: () => apiFetch<Forecast>(`/api/forecasts?${search.toString()}`),
  });
}
