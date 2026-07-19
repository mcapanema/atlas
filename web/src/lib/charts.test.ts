import { describe, expect, it, test } from "vitest";

import { snapshotsFixture } from "../test/fixtures";
import {
  buildCfdOption,
  buildForecastOption,
  buildLeadTimeDistributionOption,
  buildLeadTimeTrendOption,
  buildThroughputOption,
  buildWipOption,
  throughputTitle,
} from "./charts";

const days = [
  { day: "2026-07-01", todo: 2, in_progress: 1, done: 0 },
  { day: "2026-07-02", todo: 1, in_progress: 1, done: 1 },
];
const buckets = [
  { start: "2026-06-26T00:00:00Z", end: "2026-07-03T00:00:00Z", completed: 3 },
];
const dailyBuckets = [
  { start: "2026-07-08T00:00:00Z", end: "2026-07-09T00:00:00Z", completed: 1 },
  { start: "2026-07-09T00:00:00Z", end: "2026-07-10T00:00:00Z", completed: 2 },
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

  it("nudges overlapping end labels apart instead of letting them collide", () => {
    const option = buildCfdOption(days);
    const series = option.series as { labelLayout?: { moveOverlap?: string } }[];

    for (const s of series) {
      expect(s.labelLayout).toEqual({ moveOverlap: "shiftY" });
    }
  });

  it("keeps series colors fixed but swaps neutral furniture per theme mode", () => {
    const light = buildCfdOption(days);
    const dark = buildCfdOption(days, "dark");
    const seriesColor = (o: typeof light) => (o.series as { color: string }[])[0].color;
    const axisLabelColor = (o: typeof light) =>
      (o.xAxis as { axisLabel: { color: string } }).axisLabel.color;

    expect(seriesColor(dark)).toBe(seriesColor(light)); // validated palette, both modes
    expect(axisLabelColor(dark)).not.toBe(axisLabelColor(light));
  });
});

describe("buildThroughputOption", () => {
  it("plots one bar per bucket", () => {
    const option = buildThroughputOption(buckets, 7);
    const series = option.series as Series[];

    expect(series).toHaveLength(1);
    expect(series[0].data).toEqual([3]);
  });

  it("names a weekly bucket's full date range in the tooltip", () => {
    const option = buildThroughputOption(buckets, 7);
    const formatter = (option.tooltip as { formatter: (p: { dataIndex: number }) => string })
      .formatter;

    expect(formatter({ dataIndex: 0 })).toBe("26-06-2026 – 03-07-2026<br/>3 completed");
  });

  it("names only the day itself for a daily bucket", () => {
    const option = buildThroughputOption(dailyBuckets, 1);
    const formatter = (option.tooltip as { formatter: (p: { dataIndex: number }) => string })
      .formatter;

    expect(formatter({ dataIndex: 1 })).toBe("10-07-2026<br/>2 completed");
  });

  it("labels the y axis with the unit being counted", () => {
    const option = buildThroughputOption(buckets, 7);

    expect((option.yAxis as { name: string }).name).toBe("Items completed");
  });
});

describe("throughputTitle", () => {
  it("names the bucket size the chart is actually showing", () => {
    expect(throughputTitle(1, "7d")).toBe("Daily throughput (7d)");
    expect(throughputTitle(7, "90d")).toBe("Weekly throughput (90d)");
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
    expect((option.xAxis as { data: string[] }).data).toEqual(["20-07-2026", "22-07-2026"]);
  });
});

test("lead time trend charts P50/P85 in days per snapshot day", () => {
  const option = buildLeadTimeTrendOption(snapshotsFixture);

  const series = option.series as { name: string; data: (number | null)[] }[];
  expect(series.map((s) => s.name)).toEqual(["Lead time P50 (d)", "Lead time P85 (d)"]);
  expect(series[0].data).toEqual([2, 2]);
  expect(series[1].data).toEqual([4, 5]);
  const xAxis = option.xAxis as { data: string[] };
  expect(xAxis.data).toEqual(["09-07-2026", "10-07-2026"]);
});

test("lead time trend passes through null percentiles for snapshots with no data yet", () => {
  const option = buildLeadTimeTrendOption([
    { captured_on: "2026-07-09", lead_time_p50_seconds: null, lead_time_p85_seconds: null },
  ]);

  const series = option.series as { data: (number | null)[] }[];
  expect(series[0].data).toEqual([null]);
  expect(series[1].data).toEqual([null]);
});
