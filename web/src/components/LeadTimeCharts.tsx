import { Col } from "antd";
import { useMemo } from "react";

import type { LeadTimeDistribution } from "../api/metrics";
import type { MetricSnapshot } from "../api/snapshots";
import { buildLeadTimeDistributionOption, buildLeadTimeTrendOption } from "../lib/charts";
import { useThemeMode } from "../theme/context";
import { ChartCard, ChartEmpty } from "./ChartCard";
import { EChart } from "./EChart";

/** A line needs two points; fewer snapshots with a lead time draw nothing honest. */
const MIN_TREND_POINTS = 2;

function hasCompletions(distribution: LeadTimeDistribution): boolean {
  return distribution.bins.some((bin) => bin.count > 0);
}

function trendPoints(snapshots: MetricSnapshot[]): number {
  return snapshots.filter((snapshot) => snapshot.lead_time_p50_seconds != null).length;
}

/** The distribution and trend cards — Cols for FlowCharts' Row. */
export function LeadTimeCharts({
  distribution,
  snapshots,
  chartLabel,
}: {
  distribution: LeadTimeDistribution | undefined;
  snapshots: MetricSnapshot[] | undefined;
  chartLabel: string;
}) {
  const { mode } = useThemeMode();
  const distributionOption = useMemo(
    () =>
      distribution && hasCompletions(distribution)
        ? buildLeadTimeDistributionOption(distribution.bins, mode)
        : null,
    [distribution, mode],
  );
  const trendOption = useMemo(
    () =>
      snapshots && trendPoints(snapshots) >= MIN_TREND_POINTS
        ? buildLeadTimeTrendOption(snapshots, mode)
        : null,
    [snapshots, mode],
  );

  return (
    <>
      {distribution && (
        <Col xs={24} lg={12}>
          <ChartCard
            label={`Lead time distribution (${chartLabel})`}
            help="How many completed items fell into each lead-time bucket. A long right tail means a few items took far longer than typical."
          >
            {distributionOption ? (
              <EChart option={distributionOption} />
            ) : (
              <ChartEmpty>No items completed in this window.</ChartEmpty>
            )}
          </ChartCard>
        </Col>
      )}
      {snapshots && (
        <Col xs={24} lg={12}>
          <ChartCard
            label="Lead time trend"
            help="Daily snapshots of lead time P50 and P85. Always the unfiltered 30-day baseline, so it does not follow the filters above."
          >
            {trendOption ? (
              <EChart option={trendOption} />
            ) : (
              <ChartEmpty>
                The trend starts once two daily snapshots have a completed item.
              </ChartEmpty>
            )}
          </ChartCard>
        </Col>
      )}
    </>
  );
}
