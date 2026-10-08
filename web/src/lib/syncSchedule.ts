import type { SyncSchedule, SyncScheduleInput } from "../api/syncSchedule";

/** ISO weekdays, as the API stores them: 1 = Monday … 7 = Sunday (not getDay()). */
export const WEEKDAY_OPTIONS = [
  { value: 1, label: "Mon" },
  { value: 2, label: "Tue" },
  { value: 3, label: "Wed" },
  { value: 4, label: "Thu" },
  { value: 5, label: "Fri" },
  { value: 6, label: "Sat" },
  { value: 7, label: "Sun" },
];

const INTERVALS = [30, 60, 120, 180, 240, 360, 480, 720];

function intervalLabel(minutes: number): string {
  return minutes % 60 === 0 ? `${minutes / 60} h` : `${minutes} min`;
}

/** The interval presets, plus a saved value that isn't one (set through the API). */
export function intervalOptions(current: number) {
  const values = INTERVALS.includes(current)
    ? INTERVALS
    : [...INTERVALS, current].sort((a, b) => a - b);
  return values.map((value) => ({ value, label: intervalLabel(value) }));
}

/** IANA zones the browser knows, plus a saved zone it doesn't list (V8 omits "UTC"). */
export function timeZoneOptions(current: string) {
  const zones = Intl.supportedValuesOf("timeZone");
  const values = zones.includes(current) ? zones : [current, ...zones];
  return values.map((zone) => ({ value: zone, label: zone }));
}

/** A first schedule: working hours on weekdays, in the viewer's zone. */
export function defaultSchedule(
  timeZone = Intl.DateTimeFormat().resolvedOptions().timeZone,
): SyncScheduleInput {
  return {
    enabled: true,
    days: [1, 2, 3, 4, 5],
    window_start: "08:00",
    window_end: "18:00",
    interval_minutes: 120,
    timezone: timeZone,
  };
}

/** "08:30" or "08:30:00" → { hour: 8, minute: 30 }. */
export function clockParts(clock: string): { hour: number; minute: number } {
  return { hour: Number(clock.slice(0, 2)), minute: Number(clock.slice(3, 5)) };
}

/**
 * "08-10-2026 08:00 (America/Sao_Paulo)": an instant in the schedule's own
 * zone, labelled, so it reads the same as the window it was set in.
 */
export function formatInZone(iso: string, timeZone: string): string {
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone,
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(new Date(iso));
  const part = (type: Intl.DateTimeFormatPartTypes) =>
    parts.find((p) => p.type === type)?.value ?? "";
  return `${part("day")}-${part("month")}-${part("year")} ${part("hour")}:${part("minute")} (${timeZone})`;
}

export interface LastSync {
  at: string;
  kind: "auto" | "manual";
  error: string | null;
}

/**
 * The most recent sync, auto or manual. A manual sync after a failed auto run
 * supersedes it: the data is fresh again, so the failure is no longer news.
 */
export function lastSync(
  schedule: Pick<SyncSchedule, "last_run" | "last_manual_sync_at">,
): LastSync | null {
  const run = schedule.last_run;
  const manual = schedule.last_manual_sync_at;
  if (run && (!manual || Date.parse(run.finished_at) >= Date.parse(manual))) {
    return { at: run.finished_at, kind: "auto", error: run.error };
  }
  return manual ? { at: manual, kind: "manual", error: null } : null;
}
