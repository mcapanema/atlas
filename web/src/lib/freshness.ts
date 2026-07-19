/**
 * How far behind the analysis window the underlying data is.
 *
 * Events are append-only and stamped with `recorded_at` on ingest, so the
 * newest one dates the last sync. A window whose tail extends past that point
 * renders zeros that mean "not synced yet", not "nothing was delivered" —
 * which is the misreading this measurement exists to prevent.
 */
export const STALE_AFTER_HOURS = 24;

/** Hours between the newest record and the window end; null if there is no data. */
export function stalenessHours(dataAsOf: string | null, windowEnd: string): number | null {
  if (dataAsOf === null) return null;
  const gapMs = new Date(windowEnd).getTime() - new Date(dataAsOf).getTime();
  return Math.max(0, Math.round(gapMs / 3_600_000));
}
