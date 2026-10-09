/**
 * Delivery-health reading shared by the Executive and Team dashboards.
 * Pure — no React.
 */

import type { DeliveryHealth, HealthComponent } from "../api/metrics";

/** Warning and critical need an EM's attention; healthy and unscored don't. */
export function isAtRisk(health: DeliveryHealth | undefined): boolean {
  return health?.band === "critical" || health?.band === "warning";
}

/** The `count` lowest-scoring components — why a team scores where it does. */
export function weakestComponents(health: DeliveryHealth, count: number): HealthComponent[] {
  return [...health.components].sort((a, b) => a.score - b.score).slice(0, count);
}

// How each component is scored. These mirror app/domain/metrics/health.py;
// the scales and weights they name are the team's Metric rules.
const COMPONENT_HELP = new Map<string, string>([
  [
    "predictability",
    "How far lead time P95 sits above P50, on a log scale. P95 equal to P50 scores 100; the worst ratio in Metric rules scores 0.",
  ],
  [
    "efficiency",
    "Flow efficiency of the items completed in the window: the share of their in-progress time that was not blocked.",
  ],
  [
    "flow",
    "Throughput trend: items completed in the recent half of the window against the half before it. Holding steady or growing scores 100.",
  ],
  [
    "stability",
    "Work in progress measured in weeks of throughput. At or under the best weeks in Metric rules scores 100; at or over the worst scores 0.",
  ],
  [
    "risk",
    "Share of in-progress items that are blocked or have aged past the team's aging percentile. None at risk scores 100.",
  ],
]);

/** A component's hover definition; undefined for a name this build doesn't know. */
export function componentHelp(name: string): string | undefined {
  return COMPONENT_HELP.get(name);
}
