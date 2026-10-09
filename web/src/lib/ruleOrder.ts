/**
 * Cross-rule checks for the Metric rules form. Pure — no React.
 */

import type { MetricRules, MetricRulesView, RuleChanges, RuleName } from "../api/metricRules";
import { RULE_GROUPS } from "./metricRules";

type OrderedRule =
  | "healthy_min"
  | "warning_min"
  | "stability_best_weeks"
  | "stability_worst_weeks"
  | "predictability_floor"
  | "aging_percentile"
  | "weight_predictability"
  | "weight_efficiency"
  | "weight_flow"
  | "weight_stability"
  | "weight_risk";

function ruleLabel(name: RuleName): string {
  return RULE_GROUPS.flatMap((group) => group.rules).find((rule) => rule.name === name)!.label;
}

/**
 * The server's cross-rule checks (`_check_order` in app/domain/metric_rules),
 * so the form names a conflict before Save instead of after a 422. Ranges
 * stay on the controls' own min/max.
 */
export function orderProblems(rules: Pick<MetricRules, OrderedRule>): string[] {
  const problems: string[] = [];
  const mustBe = (low: OrderedRule, relation: "below" | "above", high: OrderedRule) =>
    problems.push(`${ruleLabel(low)} must be ${relation} ${ruleLabel(high)}.`);
  if (rules.warning_min >= rules.healthy_min) mustBe("warning_min", "below", "healthy_min");
  if (rules.stability_worst_weeks <= rules.stability_best_weeks)
    mustBe("stability_worst_weeks", "above", "stability_best_weeks");
  if (rules.predictability_floor >= rules.aging_percentile)
    mustBe("predictability_floor", "below", "aging_percentile");
  const weights = [
    rules.weight_predictability,
    rules.weight_efficiency,
    rules.weight_flow,
    rules.weight_stability,
    rules.weight_risk,
  ];
  if (!weights.some((weight) => weight > 0)) {
    problems.push("At least one health weight must be above 0.");
  }
  return problems;
}

/** The rules a draft would leave in effect: its values over the inherited ones (null = inherit). */
export function draftRules(view: Pick<MetricRulesView, "inherited">, draft: RuleChanges) {
  const own = Object.entries(draft).filter(([, value]) => value != null);
  return { ...view.inherited, ...Object.fromEntries(own) };
}
