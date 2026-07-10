import { describe, expect, it } from "vitest";

import {
  buildCfdOption,
  buildForecastOption,
  buildLeadTimeDistributionOption,
  buildThroughputOption,
  buildWipOption,
} from "./charts";

const days = [
  { day: "2026-07-01", todo: 2, in_progress: 1, done: 0 },
  { day: "2026-07-02", todo: 1, in_progress: 1, done: 1 },
];
const weeks = [
  { start: "2026-06-26T00:00:00Z", end: "2026-07-03T00:00:00Z", completed: 3 },
];

interface Series {
  name: string;
  stack?: string;
  data: number[];
}

describe("buildCfdOption", () => {
  it("stacks Done, In progress, To do bands in fixed order", () => {
    const option = buildCfdOption(days);
    const series = option.series as Series[];

    expect(series.map((s) => s.name)).toEqual(["Done", "In progress", "To do"]);
    expect(series.every((s) => s.stack === "cfd")).toBe(true);
    expect(series[0].data).toEqual([0, 1]);
    expect(series[1].data).toEqual([1, 1]);
    expect(series[2].data).toEqual([2, 1]);
    expect(option.legend).toBeDefined(); // relief: aqua/yellow are sub-3:1 on white
  });
});

describe("buildThroughputOption", () => {
  it("plots one bar per week", () => {
    const option = buildThroughputOption(weeks);
    const series = option.series as Series[];

    expect(series).toHaveLength(1);
    expect(series[0].data).toEqual([3]);
  });
});

describe("buildWipOption", () => {
  it("plots the in-progress count per day", () => {
    const option = buildWipOption(days);
    const series = option.series as Series[];

    expect(series[0].data).toEqual([1, 1]);
  });
});

describe("buildLeadTimeDistributionOption", () => {
  it("plots one bar per day bin, keeping empty bins", () => {
    const option = buildLeadTimeDistributionOption([
      { start_days: 0, end_days: 1, count: 3 },
      { start_days: 1, end_days: 2, count: 0 },
      { start_days: 2, end_days: 3, count: 1 },
    ]);
    const series = option.series as Series[];

    expect(series).toHaveLength(1);
    expect(series[0].data).toEqual([3, 0, 1]);
    expect((option.xAxis as { data: string[] }).data).toEqual(["0d", "1d", "2d"]);
  });
});

describe("buildForecastOption", () => {
  it("plots trials per completion date offset from the window end", () => {
    const option = buildForecastOption(
      [
        { days: 10, trials: 400 },
        { days: 12, trials: 1600 },
      ],
      "2026-07-10T00:00:00Z",
    );
    const series = option.series as Series[];

    expect(series[0].data).toEqual([400, 1600]);
    expect((option.xAxis as { data: string[] }).data).toEqual(["2026-07-20", "2026-07-22"]);
  });
});
