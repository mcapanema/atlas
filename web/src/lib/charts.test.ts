import { describe, expect, it } from "vitest";

import { buildCfdOption, buildThroughputOption, buildWipOption } from "./charts";

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
