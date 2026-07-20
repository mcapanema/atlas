import type { EChartsOption } from "echarts";

import { palette, type ThemeMode } from "../theme/tokens";
import { formatDay } from "./dates";

export interface DailyFlowCount {
  day: string;
  todo: number;
  in_progress: number;
  done: number;
}

export interface ThroughputBucket {
  start: string;
  end: string;
  completed: number;
}

export interface DurationBin {
  start_days: number;
  end_days: number;
  count: number;
}

export interface OutcomeBucket {
  days: number;
  trials: number;
}

// Series palette validated with the dataviz six-checks script (worst adjacent
// CVD ΔE 21.6, all in the lightness band); identical in both theme modes so a
// chart reads the same in a dark standup room and a bright office. Aqua and
// yellow sit below 3:1 contrast on a white surface — the CFD's legend + end
// labels are the required relief, don't remove them.
const SERIES = { done: "#2a78d6", inProgress: "#1baf7a", todo: "#eda100" };
const BLUE = "#2a78d6";

// Neutral chart furniture (axis labels, gridlines, legends) follows the
// theme tokens so charts sit on either surface.
interface Neutrals {
  inkSecondary: string;
  inkMuted: string;
  gridline: string;
  baseline: string;
}
function neutrals(mode: ThemeMode): Neutrals {
  const p = palette[mode];
  return {
    inkSecondary: p.inkSecondary,
    inkMuted: p.inkMuted,
    gridline: p.gridline,
    baseline: p.baseline,
  };
}

function dayAxis(labels: string[], n: Neutrals, name?: string): EChartsOption["xAxis"] {
  return {
    type: "category",
    data: labels,
    axisLabel: { color: n.inkMuted },
    axisLine: { lineStyle: { color: n.baseline } },
    name,
    nameLocation: "middle",
    nameGap: 28,
    nameTextStyle: { color: n.inkMuted },
  };
}

function valueAxis(n: Neutrals, name?: string): EChartsOption["yAxis"] {
  return {
    type: "value",
    axisLabel: { color: n.inkMuted },
    splitLine: { lineStyle: { color: n.gridline } },
    name,
    nameTextStyle: { color: n.inkMuted },
  };
}

export function buildCfdOption(
  days: DailyFlowCount[],
  mode: ThemeMode = "light",
): EChartsOption {
  const n = neutrals(mode);
  const band = (name: string, color: string, data: number[]) => ({
    name,
    type: "line" as const,
    stack: "cfd",
    data,
    color,
    symbol: "none" as const,
    lineStyle: { width: 2 },
    areaStyle: { opacity: 0.85 },
    emphasis: { focus: "series" as const },
    endLabel: { show: true, formatter: "{a}", color: n.inkSecondary },
    // Flat bands stack their end labels at the same y — shift collisions
    // apart instead of letting "In progress"/"To do" overprint.
    labelLayout: { moveOverlap: "shiftY" as const },
  });
  return {
    tooltip: { trigger: "axis" },
    legend: { bottom: 0, textStyle: { color: n.inkSecondary } },
    grid: { left: 48, right: 96, top: 16, bottom: 48 },
    xAxis: dayAxis(days.map((d) => formatDay(d.day)), n),
    yAxis: valueAxis(n),
    series: [
      band("Done", SERIES.done, days.map((d) => d.done)),
      band("In progress", SERIES.inProgress, days.map((d) => d.in_progress)),
      band("To do", SERIES.todo, days.map((d) => d.todo)),
    ],
  };
}

/** "Daily throughput (7d)" / "Weekly throughput (90d)" — name the bucket, not the window. */
export function throughputTitle(bucketDays: number, windowLabel: string): string {
  return `${bucketDays === 1 ? "Daily" : "Weekly"} throughput (${windowLabel})`;
}

export function buildThroughputOption(
  buckets: ThroughputBucket[],
  bucketDays: number,
  mode: ThemeMode = "light",
): EChartsOption {
  const n = neutrals(mode);
  return {
    tooltip: {
      trigger: "item",
      // The axis can only fit the bucket's end date, which reads as "everything
      // landed that day". For a multi-day bucket the range is what the bar
      // actually means; for a one-day bucket the end date already is the day.
      formatter: (params: unknown) => {
        const { dataIndex } = params as { dataIndex: number };
        const bucket = buckets[dataIndex];
        const when =
          bucketDays === 1
            ? formatDay(bucket.end)
            : `${formatDay(bucket.start)} – ${formatDay(bucket.end)}`;
        return `${when}<br/>${bucket.completed} completed`;
      },
    },
    grid: { left: 64, right: 16, top: 24, bottom: 32 },
    xAxis: dayAxis(buckets.map((b) => formatDay(b.end)), n),
    yAxis: valueAxis(n, "Items completed"),
    series: barSeries("Completed", buckets.map((b) => b.completed)),
  };
}

export function buildWipOption(
  days: DailyFlowCount[],
  mode: ThemeMode = "light",
): EChartsOption {
  const n = neutrals(mode);
  return {
    tooltip: { trigger: "axis" },
    grid: { left: 64, right: 16, top: 24, bottom: 32 },
    xAxis: dayAxis(days.map((d) => formatDay(d.day)), n),
    yAxis: valueAxis(n, "Items in progress"),
    series: [
      {
        name: "WIP",
        type: "line",
        color: BLUE,
        symbol: "circle",
        symbolSize: 8,
        showSymbol: false,
        lineStyle: { width: 2 },
        data: days.map((d) => d.in_progress),
      },
    ],
  };
}

function barSeries(name: string, data: number[]): EChartsOption["series"] {
  return [
    {
      name,
      type: "bar",
      color: BLUE,
      barMaxWidth: 24,
      itemStyle: { borderRadius: [4, 4, 0, 0] },
      data,
    },
  ];
}

export function buildLeadTimeDistributionOption(
  bins: DurationBin[],
  mode: ThemeMode = "light",
): EChartsOption {
  const n = neutrals(mode);
  return {
    tooltip: { trigger: "item" },
    grid: { left: 64, right: 16, top: 24, bottom: 48 },
    xAxis: dayAxis(bins.map((b) => `${b.start_days}d`), n, "Lead time"),
    yAxis: valueAxis(n, "Items completed"),
    series: barSeries("Completed items", bins.map((b) => b.count)),
  };
}

export interface LeadTimeTrendPoint {
  captured_on: string;
  lead_time_p50_seconds: number | null;
  lead_time_p85_seconds: number | null;
}

export function buildLeadTimeTrendOption(
  points: LeadTimeTrendPoint[],
  mode: ThemeMode = "light",
): EChartsOption {
  const n = neutrals(mode);
  const toDays = (seconds: number | null) =>
    seconds == null ? null : Math.round((seconds / 86_400) * 10) / 10;
  const line = (name: string, color: string, data: (number | null)[]) => ({
    name,
    type: "line" as const,
    color,
    symbol: "none" as const,
    lineStyle: { width: 2 },
    data,
  });
  return {
    tooltip: { trigger: "axis" },
    legend: { bottom: 0, textStyle: { color: n.inkSecondary } },
    grid: { left: 48, right: 16, top: 16, bottom: 48 },
    xAxis: dayAxis(points.map((p) => formatDay(p.captured_on)), n),
    yAxis: valueAxis(n),
    series: [
      line("Lead time P50 (d)", BLUE, points.map((p) => toDays(p.lead_time_p50_seconds))),
      line(
        "Lead time P85 (d)",
        SERIES.inProgress,
        points.map((p) => toDays(p.lead_time_p85_seconds)),
      ),
    ],
  };
}

/** Percentile finish dates, ISO — drawn on the histogram as reference lines. */
export interface ForecastPercentiles {
  p50Date: string;
  p85Date: string;
}

export function buildForecastOption(
  outcomes: OutcomeBucket[],
  windowEnd: string,
  percentiles: ForecastPercentiles,
  mode: ThemeMode = "light",
): EChartsOption {
  const n = neutrals(mode);
  const origin = new Date(windowEnd).getTime();
  const label = (days: number) => formatDay(new Date(origin + days * 86_400_000).toISOString());
  const labels = outcomes.map((o) => label(o.days));
  const total = outcomes.reduce((sum, o) => sum + o.trials, 0);

  // A percentile day can land between two occupied buckets (outcomes at 10 and
  // 12 days, P50 at 11). Snap forward to the first bucket at or after it and
  // reuse that bucket's own axis label: keying a markLine on a date string the
  // category axis never emitted would silently draw nothing.
  const markAt = (iso: string, name: string) => {
    const days = Math.round((new Date(iso).getTime() - origin) / 86_400_000);
    const index = outcomes.findIndex((o) => o.days >= days);
    return {
      xAxis: labels[index === -1 ? labels.length - 1 : index],
      label: { formatter: name, color: n.inkSecondary },
      lineStyle: { color: n.inkSecondary, type: "dashed" as const },
    };
  };

  const series = barSeries("Simulations", outcomes.map((o) => o.trials)) as [
    Record<string, unknown>,
  ];
  series[0].markLine = {
    silent: true,
    symbol: "none",
    data: [markAt(percentiles.p50Date, "P50"), markAt(percentiles.p85Date, "P85")],
  };

  return {
    tooltip: {
      trigger: "item",
      // "1600" on its own reads as a quantity of work. It is a count of
      // simulated futures — say so, and give the share it represents.
      formatter: (params: unknown) => {
        const { dataIndex } = params as { dataIndex: number };
        const bucket = outcomes[dataIndex];
        const share = ((bucket.trials / total) * 100).toFixed(1);
        return `${bucket.trials.toLocaleString("en-US")} of ${total.toLocaleString("en-US")} simulations finished by ${labels[dataIndex]} (${share}%)`;
      },
    },
    grid: { left: 56, right: 16, top: 32, bottom: 56 },
    xAxis: dayAxis(labels, n, "Forecast finish date"),
    yAxis: valueAxis(n, "Simulations"),
    series: series as EChartsOption["series"],
  };
}
