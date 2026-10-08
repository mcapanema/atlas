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
