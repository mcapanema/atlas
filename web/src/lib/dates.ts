import dayjs from "dayjs";

/** The display format for every user-facing date. Also the AntD picker format. */
export const DATE_FORMAT = "DD-MM-YYYY";

/**
 * "10-06-2026" — every user-facing date.
 *
 * Read in UTC: these are calendar dates (window bounds, snapshot days,
 * forecast finishes), so formatting them in a local zone west of Greenwich
 * would show the previous day. ponytail: hand-built from the Date's UTC
 * parts rather than pulling in dayjs's utc plugin for three lines.
 */
export function formatDay(iso: string): string {
  const date = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${pad(date.getUTCDate())}-${pad(date.getUTCMonth() + 1)}-${date.getUTCFullYear()}`;
}

/** "10-06-2026 14:32" — a point in time, in the viewer's local zone. */
export function formatDateTime(iso: string): string {
  return dayjs(iso).format(`${DATE_FORMAT} HH:mm`);
}
