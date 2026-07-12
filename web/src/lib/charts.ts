import type { EChartsOption } from "echarts";

import { palette, type ThemeMode } from "../theme/tokens";

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

function dayAxis(labels: string[], n: Neutrals): EChartsOption["xAxis"] {
  return {
    type: "category",
    data: labels,
    axisLabel: { color: n.inkMuted },
    axisLine: { lineStyle: { color: n.baseline } },
  };
}

function valueAxis(n: Neutrals): EChartsOption["yAxis"] {
  return {
    type: "value",
    axisLabel: { color: n.inkMuted },
    splitLine: { lineStyle: { color: n.gridline } },
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
    xAxis: dayAxis(days.map((d) => d.day), n),
    yAxis: valueAxis(n),
    series: [
      band("Done", SERIES.done, days.map((d) => d.done)),
      band("In progress", SERIES.inProgress, days.map((d) => d.in_progress)),
      band("To do", SERIES.todo, days.map((d) => d.todo)),
    ],
  };
}

export function buildThroughputOption(
  weeks: ThroughputBucket[],
  mode: ThemeMode = "light",
): EChartsOption {
  const n = neutrals(mode);
  return {
    tooltip: { trigger: "item" },
    grid: { left: 48, right: 16, top: 16, bottom: 32 },
    xAxis: dayAxis(weeks.map((w) => w.end.slice(0, 10)), n),
    yAxis: valueAxis(n),
    series: barSeries("Completed", weeks.map((w) => w.completed)),
  };
}

export function buildWipOption(
  days: DailyFlowCount[],
  mode: ThemeMode = "light",
): EChartsOption {
  const n = neutrals(mode);
  return {
    tooltip: { trigger: "axis" },
    grid: { left: 48, right: 16, top: 16, bottom: 32 },
    xAxis: dayAxis(days.map((d) => d.day), n),
    yAxis: valueAxis(n),
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
    grid: { left: 48, right: 16, top: 16, bottom: 32 },
    xAxis: dayAxis(bins.map((b) => `${b.start_days}d`), n),
    yAxis: valueAxis(n),
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
    xAxis: dayAxis(points.map((p) => p.captured_on), n),
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

export function buildForecastOption(
  outcomes: OutcomeBucket[],
  windowEnd: string,
  mode: ThemeMode = "light",
): EChartsOption {
  const n = neutrals(mode);
  const origin = new Date(windowEnd).getTime();
  const label = (days: number) =>
    new Date(origin + days * 86_400_000).toISOString().slice(0, 10);
  return {
    tooltip: { trigger: "item" },
    grid: { left: 48, right: 16, top: 16, bottom: 32 },
    xAxis: dayAxis(outcomes.map((o) => label(o.days)), n),
    yAxis: valueAxis(n),
    series: barSeries("Trials", outcomes.map((o) => o.trials)),
  };
}
