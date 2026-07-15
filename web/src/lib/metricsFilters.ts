import type { MetricsFilters } from "../api/metrics";
import { formatDay } from "./dates";

/** URL keys: window, start, end, types (comma-joined), xstates (comma-joined). */
const KEYS = ["window", "start", "end", "types", "xstates"] as const;

export function filtersFromSearchParams(params: URLSearchParams): MetricsFilters {
  const filters: MetricsFilters = {};
  const window = params.get("window");
  if (window) filters.windowDays = Number(window);
  const start = params.get("start");
  const end = params.get("end");
  if (start && end) {
    filters.start = start;
    filters.end = end;
  }
  const types = params.get("types");
  if (types) filters.types = types.split(",");
  const xstates = params.get("xstates");
  if (xstates) filters.excludeStates = xstates.split(",");
  return filters;
}

export function applyFiltersToSearchParams(
  params: URLSearchParams,
  filters: MetricsFilters,
): void {
  for (const key of KEYS) params.delete(key);
  if (filters.start && filters.end) {
    params.set("start", filters.start);
    params.set("end", filters.end);
  } else if (filters.windowDays !== undefined) {
    params.set("window", String(filters.windowDays));
  }
  if (filters.types?.length) params.set("types", filters.types.join(","));
  if (filters.excludeStates?.length) params.set("xstates", filters.excludeStates.join(","));
}

export function windowLabel(filters: MetricsFilters, defaultDays: number): string {
  if (filters.start && filters.end) {
    return `${formatDay(filters.start)} – ${formatDay(filters.end)}`;
  }
  return `${filters.windowDays ?? defaultDays}d`;
}

/** True when the view matches the persisted-snapshot baseline (30d, no item filters). */
export function isDefaultFilters(filters: MetricsFilters): boolean {
  return (
    !filters.start &&
    (filters.windowDays === undefined || filters.windowDays === 30) &&
    !filters.types?.length &&
    !filters.excludeStates?.length
  );
}
