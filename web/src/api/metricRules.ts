import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiFetch } from "./client";

/** Every rule that changes how a metric is computed (app/domain/metric_rules). */
export interface MetricRules {
  exclude_born_done: boolean;
  move_back_ends_wip: boolean;
  restart_clock_after_move_back: boolean;
  reopen_completion: "last" | "first";
  done_then_canceled: "delivered" | "canceled";
  healthy_min: number;
  warning_min: number;
  predictability_worst_ratio: number;
  stability_best_weeks: number;
  stability_worst_weeks: number;
  aging_percentile: number;
  weight_predictability: number;
  weight_efficiency: number;
  weight_flow: number;
  weight_stability: number;
  weight_risk: number;
  timezone: string;
  daily_bucket_max_days: number;
  forecast_history_days: number;
}

export type RuleName = keyof MetricRules;
export type RuleValue = MetricRules[RuleName];
/** A PATCH body: a value overrides the rule, null makes it inherit again. */
export type RuleChanges = Partial<Record<RuleName, RuleValue | null>>;

export interface RecomputeStatus {
  state: "idle" | "running" | "failed";
  started_at: string | null;
  finished_at: string | null;
  error: string | null;
}

export interface MetricRulesView {
  built_in: MetricRules;
  inherited: MetricRules;
  overrides: Partial<MetricRules>;
  effective: MetricRules;
  recompute: RecomputeStatus;
}

/** The workspace default (an organization) or one team. */
export type RulesScope = { kind: "organization"; id: string } | { kind: "team"; id: string };

const POLL_MS = 2_000;

function rulesPath(scope: RulesScope): string {
  const collection = scope.kind === "organization" ? "organizations" : "teams";
  return `/api/${collection}/${scope.id}/metric-rules`;
}

function rulesKey(scope: RulesScope | undefined) {
  return ["metric-rules", scope?.kind, scope?.id] as const;
}

export function useMetricRules(scope: RulesScope | undefined) {
  return useQuery({
    queryKey: rulesKey(scope),
    queryFn: () => apiFetch<MetricRulesView>(rulesPath(scope as RulesScope)),
    enabled: scope !== undefined,
    // Poll while the history rewrite runs, so the banner clears by itself.
    refetchInterval: (query) => (query.state.data?.recompute.state === "running" ? POLL_MS : false),
  });
}

export function useSaveMetricRules(scope: RulesScope) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (changes: RuleChanges) =>
      apiFetch<MetricRulesView>(rulesPath(scope), {
        method: "PATCH",
        body: JSON.stringify(changes),
      }),
    onSuccess: (view) => {
      queryClient.setQueryData(rulesKey(scope), view);
      // Rules move numbers on every page: refetch everything else cached.
      void queryClient.invalidateQueries({
        predicate: (query) => query.queryKey[0] !== "metric-rules",
      });
    },
  });
}

export function useRecomputeHistory(organizationId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => {
      if (organizationId === undefined) throw new Error("No organization to recompute");
      return apiFetch<MetricRulesView>(
        `/api/organizations/${organizationId}/metric-rules/recompute`,
        {
          method: "POST",
        },
      );
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["metric-rules"] }),
  });
}
