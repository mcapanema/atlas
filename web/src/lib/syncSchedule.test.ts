import { afterEach, describe, expect, it, vi } from "vitest";

import {
  WEEKDAY_OPTIONS,
  clockParts,
  defaultSchedule,
  formatInZone,
  intervalOptions,
  timeZoneOptions,
} from "./syncSchedule";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("syncSchedule helpers", () => {
  it("numbers weekdays the ISO way, Monday 1 through Sunday 7", () => {
    expect(WEEKDAY_OPTIONS[0]).toEqual({ value: 1, label: "Mon" });
    expect(WEEKDAY_OPTIONS[6]).toEqual({ value: 7, label: "Sun" });
  });

  it("labels intervals in hours or minutes", () => {
    const labels = intervalOptions(120).map((option) => option.label);
    expect(labels).toEqual(["30 min", "1 h", "2 h", "3 h", "4 h", "6 h", "8 h", "12 h"]);
  });

  it("intervalOptions keeps a saved interval that is not a preset", () => {
    expect(intervalOptions(90).map((option) => option.value)).toEqual([
      30, 60, 90, 120, 180, 240, 360, 480, 720,
    ]);
    expect(intervalOptions(90)).toContainEqual({ value: 90, label: "90 min" });
  });

  it("timeZoneOptions keeps a saved zone the browser does not list", () => {
    vi.spyOn(Intl, "supportedValuesOf").mockReturnValue(["America/Sao_Paulo"]);

    expect(timeZoneOptions("UTC").map((option) => option.value)).toEqual([
      "UTC",
      "America/Sao_Paulo",
    ]);
    expect(timeZoneOptions("America/Sao_Paulo").map((option) => option.value)).toEqual([
      "America/Sao_Paulo",
    ]);
  });

  it("defaults a new schedule to weekdays, 08:00 to 18:00, every 2 h", () => {
    expect(defaultSchedule("America/Sao_Paulo")).toEqual({
      enabled: true,
      days: [1, 2, 3, 4, 5],
      window_start: "08:00",
      window_end: "18:00",
      interval_minutes: 120,
      timezone: "America/Sao_Paulo",
    });
  });

  it("reads hours and minutes from HH:MM and HH:MM:SS", () => {
    expect(clockParts("08:30:00")).toEqual({ hour: 8, minute: 30 });
    expect(clockParts("18:05")).toEqual({ hour: 18, minute: 5 });
  });

  it("formats an instant in the schedule's zone, labelled with it", () => {
    expect(formatInZone("2026-10-08T11:00:00Z", "America/Sao_Paulo")).toBe(
      "08-10-2026 08:00 (America/Sao_Paulo)",
    );
    expect(formatInZone("2026-10-08T23:30:00Z", "Asia/Tokyo")).toBe(
      "09-10-2026 08:30 (Asia/Tokyo)",
    );
  });
});
