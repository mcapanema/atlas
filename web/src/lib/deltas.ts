/**
 * Window-over-window deltas and short-horizon pulses, computed from the
 * persisted daily metric snapshots. Pure functions — `asOf` is always passed
 * in (the metrics API's own window_end) so results are deterministic.
 */

import type { MetricSnapshot } from "../api/snapshots";

const DAY_MS = 86_400_000;

function capturedAt(snapshot: MetricSnapshot): number {
  return new Date(`${snapshot.captured_on}T00:00:00Z`).getTime();
}

/**
 * The snapshot closest to `daysAgo` before `asOf`, or null when the nearest
 * capture is more than `toleranceDays` off target (sparse/fresh history —
 * better no delta than a misleading one).
 */
export function pickBaseline(
  snapshots: MetricSnapshot[],
  asOf: string,
  daysAgo: number,
  toleranceDays = 7,
): MetricSnapshot | null {
  const target = new Date(asOf).getTime() - daysAgo * DAY_MS;
  let best: MetricSnapshot | null = null;
  let bestDistance = Infinity;
  for (const snapshot of snapshots) {
    const distance = Math.abs(capturedAt(snapshot) - target);
    if (distance < bestDistance) {
      best = snapshot;
      bestDistance = distance;
    }
  }
  return best !== null && bestDistance <= toleranceDays * DAY_MS ? best : null;
}

export interface Delta {
  /** Signed fraction vs baseline: +0.38 = 38% above the prior window. */
  pct: number;
  direction: "up" | "down" | "flat";
  /** Whether the move is favorable; null when flat. */
  good: boolean | null;
  /** captured_on of the baseline snapshot, for the explanatory tooltip. */
  baselineDate: string;
}

/** Change of `current` vs `baseline`; sub-0.5% moves report as flat. */
export function computeDelta(
  current: number | null | undefined,
  baseline: number | null | undefined,
  lowerIsBetter: boolean,
  baselineDate: string,
): Delta | null {
  if (current == null || baseline == null || baseline === 0) return null;
  const pct = (current - baseline) / baseline;
  if (Math.abs(pct) < 0.005) return { pct: 0, direction: "flat", good: null, baselineDate };
  const direction = pct > 0 ? "up" : "down";
  return { pct, direction, good: lowerIsBetter ? pct < 0 : pct > 0, baselineDate };
}

export interface Pulse {
  /** Chronological lead-time-P85 values inside the pulse window. */
  points: number[];
  trend: "improving" | "worsening" | "steady";
}

/**
 * Short-horizon lead-time-P85 pulse: the last `days` of snapshot captures.
 * Null with fewer than two usable points — a one-point "trend" is noise.
 */
export function leadTimePulse(
  snapshots: MetricSnapshot[],
  asOf: string,
  days = 7,
): Pulse | null {
  const cutoff = new Date(asOf).getTime() - days * DAY_MS;
  const points = [...snapshots]
    .filter((snapshot) => capturedAt(snapshot) >= cutoff)
    .sort((a, b) => a.captured_on.localeCompare(b.captured_on))
    .map((snapshot) => snapshot.lead_time_p85_seconds)
    .filter((value): value is number => value != null);
  if (points.length < 2) return null;
  const first = points[0];
  const last = points[points.length - 1];
  let trend: Pulse["trend"];
  if (first === 0) {
    trend = last > 0 ? "worsening" : "steady";
  } else {
    const change = (last - first) / first;
    trend = Math.abs(change) < 0.05 ? "steady" : change > 0 ? "worsening" : "improving";
  }
  return { points, trend };
}
