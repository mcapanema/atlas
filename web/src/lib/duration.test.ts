import { afterEach, describe, expect, it, vi } from "vitest";

import { formatDuration, formatSeconds } from "./duration";

afterEach(() => {
  vi.useRealTimers();
});

describe("formatDuration", () => {
  it("formats closed periods as days/hours/minutes", () => {
    expect(formatDuration("2026-01-01T00:00:00Z", "2026-01-03T05:00:00Z")).toBe("2d 5h");
    expect(formatDuration("2026-01-01T00:00:00Z", "2026-01-01T02:15:00Z")).toBe("2h 15m");
    expect(formatDuration("2026-01-01T00:00:00Z", "2026-01-01T00:05:00Z")).toBe("5m");
    expect(formatDuration("2026-01-01T00:00:00Z", "2026-01-01T00:00:30Z")).toBe("< 1m");
  });

  it("omits minutes when a whole number of hours has elapsed", () => {
    expect(formatDuration("2026-01-01T00:00:00Z", "2026-01-01T02:00:00Z")).toBe("2h");
  });

  it("measures open periods against the current time", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-01-02T00:00:00Z"));

    expect(formatDuration("2026-01-01T00:00:00Z", null)).toBe("1d");
  });
});

describe("formatSeconds", () => {
  it("renders zero as 0m", () => {
    expect(formatSeconds(0)).toBe("0m");
  });

  it("renders sub-minute values as < 1m", () => {
    expect(formatSeconds(30)).toBe("< 1m");
  });

  it("renders minutes", () => {
    expect(formatSeconds(300)).toBe("5m");
  });

  it("renders days and hours", () => {
    expect(formatSeconds(2 * 86400 + 3 * 3600)).toBe("2d 3h");
  });

  it("drops hours once a duration reaches a week", () => {
    expect(formatSeconds(94 * 86400 + 7 * 3600)).toBe("94d");
    expect(formatSeconds(7 * 86400 + 3 * 3600)).toBe("7d");
  });

  it("rounds week-plus durations to the nearest day instead of truncating", () => {
    // A P85 of 7d 23h must not read as 7d — that understates it by 14%.
    expect(formatSeconds(7 * 86400 + 23 * 3600)).toBe("8d");
    expect(formatSeconds(7 * 86400 + 11 * 3600)).toBe("7d");
  });

  it("keeps hours just under a week", () => {
    expect(formatSeconds(6 * 86400 + 23 * 3600)).toBe("6d 23h");
  });
});
