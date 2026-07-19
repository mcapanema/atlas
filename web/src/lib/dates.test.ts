import { describe, expect, it } from "vitest";

import { DATE_FORMAT, formatDateTime, formatDay } from "./dates";

describe("formatDay", () => {
  it("renders a date-only ISO string as DD-MM-YYYY", () => {
    expect(formatDay("2026-06-10")).toBe("10-06-2026");
  });

  it("renders a full ISO timestamp as DD-MM-YYYY", () => {
    expect(formatDay("2026-07-10T00:00:00Z")).toBe("10-07-2026");
  });

  it("zero-pads single-digit days and months", () => {
    expect(formatDay("2026-01-05")).toBe("05-01-2026");
  });

  it("reads a date-only value in UTC, not the local zone", () => {
    // A UTC-negative local zone would otherwise roll this back to the 9th.
    expect(formatDay("2026-06-10T00:00:00Z")).toBe("10-06-2026");
  });
});

describe("formatDateTime", () => {
  it("renders a timestamp as DD-MM-YYYY HH:mm in 24-hour time", () => {
    expect(formatDateTime("2026-06-10T14:32:07Z")).toBe("10-06-2026 14:32");
  });

  it("zero-pads the hour and drops seconds", () => {
    expect(formatDateTime("2026-06-10T09:05:59Z")).toBe("10-06-2026 09:05");
  });
});

describe("DATE_FORMAT", () => {
  it("is the dayjs pattern the AntD pickers display", () => {
    expect(DATE_FORMAT).toBe("DD-MM-YYYY");
  });
});
