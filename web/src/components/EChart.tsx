import type { EChartsOption } from "echarts";
import { BarChart, LineChart } from "echarts/charts";
import { GridComponent, LegendComponent, MarkLineComponent, TooltipComponent } from "echarts/components";
import * as echarts from "echarts/core";
import type { EChartsType } from "echarts/core";
import { LabelLayout } from "echarts/features";
import { CanvasRenderer } from "echarts/renderers";
import { useEffect, useRef } from "react";

// Exactly what the option builders in ../lib/charts.ts use. LabelLayout backs
// the CFD's endLabel. Adding a new chart/component type to charts.ts requires
// registering its module here — a missing registration fails at runtime, not
// in tests (jsdom mocks EChart).
echarts.use([
  LineChart,
  BarChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  MarkLineComponent,
  LabelLayout,
  CanvasRenderer,
]);

export function EChart({ option, height = 260 }: { option: EChartsOption; height?: number }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<EChartsType | null>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const chart = echarts.init(container);
    chartRef.current = chart;
    const observer = new ResizeObserver(() => chart.resize());
    observer.observe(container);
    return () => {
      observer.disconnect();
      chart.dispose();
      chartRef.current = null;
    };
  }, []);

  useEffect(() => {
    chartRef.current?.setOption(option, true);
  }, [option]);

  return <div ref={containerRef} style={{ width: "100%", height }} />;
}
