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
});
