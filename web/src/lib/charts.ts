import type { EChartsOption } from "echarts";

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

// Palette validated with the dataviz six-checks script (worst adjacent CVD
// ΔE 21.6, all in the lightness band). Aqua and yellow sit below 3:1
// contrast on a white surface — the CFD's legend + end labels are the
// required relief, don't remove them.
const SERIES = { done: "#2a78d6", inProgress: "#1baf7a", todo: "#eda100" };
const BLUE = "#2a78d6";
const INK_SECONDARY = "#52514e";
const INK_MUTED = "#898781";
const GRIDLINE = "#e1e0d9";
const BASELINE = "#c3c2b7";

function dayAxis(labels: string[]): EChartsOption["xAxis"] {
  return {
    type: "category",
    data: labels,
    axisLabel: { color: INK_MUTED },
    axisLine: { lineStyle: { color: BASELINE } },
  };
}

function valueAxis(): EChartsOption["yAxis"] {
  return {
    type: "value",
    axisLabel: { color: INK_MUTED },
    splitLine: { lineStyle: { color: GRIDLINE } },
  };
}

export function buildCfdOption(days: DailyFlowCount[]): EChartsOption {
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
    endLabel: { show: true, formatter: "{a}", color: INK_SECONDARY },
  });
  return {
    tooltip: { trigger: "axis" },
    legend: { bottom: 0, textStyle: { color: INK_SECONDARY } },
    grid: { left: 48, right: 96, top: 16, bottom: 48 },
    xAxis: dayAxis(days.map((d) => d.day)),
    yAxis: valueAxis(),
    series: [
      band("Done", SERIES.done, days.map((d) => d.done)),
      band("In progress", SERIES.inProgress, days.map((d) => d.in_progress)),
      band("To do", SERIES.todo, days.map((d) => d.todo)),
    ],
  };
}

export function buildThroughputOption(weeks: ThroughputBucket[]): EChartsOption {
  return {
    tooltip: { trigger: "item" },
    grid: { left: 48, right: 16, top: 16, bottom: 32 },
    xAxis: dayAxis(weeks.map((w) => w.end.slice(0, 10))),
    yAxis: valueAxis(),
    series: [
      {
        name: "Completed",
        type: "bar",
        color: BLUE,
        barMaxWidth: 24,
        itemStyle: { borderRadius: [4, 4, 0, 0] },
        data: weeks.map((w) => w.completed),
      },
    ],
  };
}

export function buildWipOption(days: DailyFlowCount[]): EChartsOption {
  return {
    tooltip: { trigger: "axis" },
    grid: { left: 48, right: 16, top: 16, bottom: 32 },
    xAxis: dayAxis(days.map((d) => d.day)),
    yAxis: valueAxis(),
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

export function buildLeadTimeDistributionOption(bins: DurationBin[]): EChartsOption {
  return {
    tooltip: { trigger: "item" },
    grid: { left: 48, right: 16, top: 16, bottom: 32 },
    xAxis: dayAxis(bins.map((b) => `${b.start_days}d`)),
    yAxis: valueAxis(),
    series: barSeries("Completed items", bins.map((b) => b.count)),
  };
}

export function buildForecastOption(
  outcomes: OutcomeBucket[],
  windowEnd: string,
): EChartsOption {
  const origin = new Date(windowEnd).getTime();
  const label = (days: number) =>
    new Date(origin + days * 86_400_000).toISOString().slice(0, 10);
  return {
    tooltip: { trigger: "item" },
    grid: { left: 48, right: 16, top: 16, bottom: 32 },
    xAxis: dayAxis(outcomes.map((o) => label(o.days))),
    yAxis: valueAxis(),
    series: barSeries("Trials", outcomes.map((o) => o.trials)),
  };
}
