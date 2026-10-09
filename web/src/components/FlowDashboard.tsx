import { Alert, Card, Col, Row, Skeleton, Space, Table, Tag } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useMemo, type ReactNode } from "react";
import { Link } from "react-router-dom";

import {
  useAgingWip,
  useDeliveryHealth,
  useFlowHistory,
  useFlowMetrics,
  useLeadTimeDistribution,
  type AgingItem,
  type DeliveryHealth,
  type DurationStats,
  type FlowHistory,
  type FlowMetrics,
  type LeadTimeDistribution,
  type MetricsFilters,
  type MetricsScope,
} from "../api/metrics";
import { useMetricSnapshots, type MetricSnapshot } from "../api/snapshots";
import {
  buildCfdOption,
  buildLeadTimeDistributionOption,
  buildLeadTimeTrendOption,
  buildThroughputOption,
  buildWipOption,
  throughputTitle,
} from "../lib/charts";
import { formatDateTime } from "../lib/dates";
import { formatSeconds } from "../lib/duration";
import { STALE_AFTER_HOURS, stalenessHours } from "../lib/freshness";
import { isAtRisk, weakestComponents } from "../lib/health";
import { isRanged, periodText, windowLabel } from "../lib/metricsFilters";
import { useThemeMode } from "../theme/context";
import { EChart } from "./EChart";
import { ForecastCard } from "./ForecastCard";
import { HealthBadge } from "./HealthBadge";
import { HelpLabel } from "./HelpLabel";
import { StatCard } from "./StatCard";

function agingColumns(percentile: number): ColumnsType<AgingItem> {
  return [
    {
      title: "Title",
      dataIndex: "title",
      render: (title, item) => <Link to={`/work-items/${item.work_item_id}`}>{title}</Link>,
    },
    { title: "State", dataIndex: "state" },
    { title: "Age", className: "fig", render: (_, item) => formatSeconds(item.age_seconds) },
    {
      title: "",
      render: (_, item) =>
        item.over_percentile ? <Tag color="red">over P{percentile}</Tag> : null,
    },
  ];
}

function duration(stats: DurationStats | null, key: keyof DurationStats): string {
  return stats ? formatSeconds(stats[key]) : "—";
}

/**
 * Health leads the page — same vocabulary as the executive dashboard:
 * quiet badge + window when healthy; the two weakest component reasons,
 * tinted by band, when at risk.
 */
function HealthStrip({
  health,
  periodText,
}: {
  health: DeliveryHealth;
  periodText: string | null;
}) {
  const atRisk = isAtRisk(health);
  const reasons = atRisk ? weakestComponents(health, 2) : [];
  return (
    <section aria-label="Delivery health" className="health-strip">
      <div className="health-strip__row">
        <HealthBadge health={health} />
        {periodText && <span className="page-asof">{periodText}</span>}
      </div>
      {atRisk && (
        <div className={`attention-card attention-card--${health.band}`}>
          <ul className="attention-card__reasons">
            {reasons.map((component) => (
              <li key={component.name}>
                <strong>{component.name}</strong> {component.reason}
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}

/** Warns when the window's tail has no synced data, so zeros aren't misread. */
function StaleDataAlert({ history }: { history: FlowHistory }) {
  const staleHours = stalenessHours(history.data_as_of, history.window_end);
  if (history.data_as_of === null || staleHours === null || staleHours <= STALE_AFTER_HOURS) {
    return null;
  }
  const staleDays = Math.floor(staleHours / 24);
  const tail =
    staleDays === 1 ? "last day of this window is" : `last ${staleDays} days of this window are`;
  // One line: the warning qualifies the charts below, it isn't the page's news.
  return (
    <Alert
      type="warning"
      showIcon
      title={`Data last synced ${formatDateTime(history.data_as_of)} — the ${tail} not ingested yet, so its zeros don't mean nothing was delivered.`}
    />
  );
}

function FlowStats({
  data,
  statLabel,
  ranged,
}: {
  data: FlowMetrics;
  statLabel: string;
  ranged: boolean;
}) {
  // Five columns of pairs — volume, lead time, cycle time, time split,
  // waste — so each P50 reads directly against its P85.
  return (
    <div className="stat-grid stat-grid--paired">
      <StatCard
        title={`Throughput (${statLabel})`}
        value={data.completed}
        help={`Work items completed in the last ${statLabel}. Counted at the moment an item reached a done state. Items created already done (logged after the fact) are left out of every metric, unless the team's metric rules include them.`}
      />
      <StatCard
        title={ranged ? "WIP (at range end)" : "WIP (now)"}
        value={data.wip}
        help={
          ranged
            ? "Work items in progress at the end of the selected range: started, and not yet completed, moved back, or canceled by then. Not an average over the range."
            : "Work items in progress right now: started, and not yet completed, moved back, or canceled. Not an average over the window."
        }
      />
      <StatCard
        title="Lead time P50"
        value={duration(data.lead_time, "p50_seconds")}
        help="Median time from an item being created to being completed. Half of completed items took less than this."
      />
      <StatCard
        title="Lead time P85"
        value={duration(data.lead_time, "p85_seconds")}
        help="85% of items went from created to completed in this time or less. The number to quote when committing to a date."
      />
      <StatCard
        title="Cycle time P50"
        value={duration(data.cycle_time, "p50_seconds")}
        help="Median time from work starting on an item to it being completed. Excludes the wait before it was picked up."
      />
      <StatCard
        title="Cycle time P85"
        value={duration(data.cycle_time, "p85_seconds")}
        help="85% of items went from started to completed in this time or less."
      />
      <StatCard
        title="Queue time P50"
        value={duration(data.queue_time, "p50_seconds")}
        help="Median time an item waited between being created and work starting."
      />
      <StatCard
        title="Touch time P50"
        value={duration(data.touch_time, "p50_seconds")}
        help="Median time an item spent actively worked on, excluding queued and blocked time."
      />
      <StatCard
        title={`Blocked time (${statLabel})`}
        value={formatSeconds(data.blocked_seconds)}
        help={`Time the items completed in the last ${statLabel} spent blocked while in progress (start to done), summed across items.`}
      />
      <StatCard
        title="Flow efficiency"
        value={data.flow_efficiency != null ? `${Math.round(data.flow_efficiency * 100)}%` : "—"}
        help="Touch time divided by lead time. The share of an item's life that was active work rather than waiting."
      />
    </div>
  );
}

function ChartCard({
  label,
  help,
  children,
}: {
  label: string;
  help: string;
  children: ReactNode;
}) {
  return <Card title={<HelpLabel label={label} help={help} />}>{children}</Card>;
}

function FlowCharts({
  history,
  distribution,
  snapshots,
  chartLabel,
}: {
  history: FlowHistory;
  distribution: LeadTimeDistribution | undefined;
  snapshots: MetricSnapshot[] | undefined;
  chartLabel: string;
}) {
  const { mode } = useThemeMode();
  const cfdOption = useMemo(() => buildCfdOption(history.days, mode), [history, mode]);
  const wipOption = useMemo(() => buildWipOption(history.days, mode), [history, mode]);
  const throughputOption = useMemo(
    // ponytail: one bucket is not a trend — it restates the Throughput stat
    // tile as a single bar. Short windows now bucket daily upstream, so this
    // guard is a safety net rather than the common path.
    () =>
      history.buckets.length > 1
        ? buildThroughputOption(history.buckets, history.bucket_days, mode)
        : null,
    [history, mode],
  );
  const distributionOption = useMemo(
    () => (distribution ? buildLeadTimeDistributionOption(distribution.bins, mode) : null),
    [distribution, mode],
  );
  const trendOption = useMemo(
    () => (snapshots && snapshots.length > 0 ? buildLeadTimeTrendOption(snapshots, mode) : null),
    [snapshots, mode],
  );

  return (
    <Row gutter={[16, 16]}>
      <Col xs={24}>
        <ChartCard
          label={`Cumulative flow (${chartLabel})`}
          help="How many items sat in each state on each day of the window. Widening bands mean work arriving faster than it leaves."
        >
          <EChart option={cfdOption} height={300} />
        </ChartCard>
      </Col>
      {throughputOption && (
        <Col xs={24} lg={12}>
          <ChartCard
            label={throughputTitle(history.bucket_days, chartLabel)}
            help={
              history.bucket_days === 1
                ? "Work items completed on each day of the window. Windows of 21 days or fewer bucket per day."
                : "Work items completed in each trailing 7-day bucket, oldest first. Longer windows bucket per week to keep the shape readable; the oldest bucket is shorter when the window isn't a whole number of weeks."
            }
          >
            <EChart option={throughputOption} />
          </ChartCard>
        </Col>
      )}
      <Col xs={24} lg={12}>
        <ChartCard
          label={`WIP over time (${chartLabel})`}
          help="Items in progress at the end of each day. A rising line means work is being started faster than it is finished."
        >
          <EChart option={wipOption} />
        </ChartCard>
      </Col>
      {distributionOption && (
        <Col xs={24} lg={12}>
          <ChartCard
            label={`Lead time distribution (${chartLabel})`}
            help="How many completed items fell into each lead-time bucket. A long right tail means a few items took far longer than typical."
          >
            <EChart option={distributionOption} />
          </ChartCard>
        </Col>
      )}
      {trendOption && (
        <Col xs={24} lg={12}>
          <ChartCard
            label="Lead time trend"
            help="Daily snapshots of lead time P50 and P85. Always the unfiltered 30-day baseline, so it does not follow the filters above."
          >
            <EChart option={trendOption} />
          </ChartCard>
        </Col>
      )}
    </Row>
  );
}

function AgingWipCard({ items, percentile }: { items: AgingItem[]; percentile: number }) {
  return (
    <ChartCard
      label="Aging WIP"
      help={`Items currently in progress, oldest first. Flagged when they have already been open longer than ${percentile}% of completed items took (the team's aging percentile, set in Metric rules).`}
    >
      <Table
        size="small"
        rowKey="work_item_id"
        pagination={false}
        columns={agingColumns(percentile)}
        dataSource={items}
      />
    </ChartCard>
  );
}

export function FlowDashboard({
  scope,
  filters = {},
}: {
  scope: MetricsScope;
  filters?: MetricsFilters;
}) {
  const metrics = useFlowMetrics(scope, filters);
  const history = useFlowHistory(scope, filters);
  const distribution = useLeadTimeDistribution(scope, filters);
  const snapshots = useMetricSnapshots(scope); // persisted trend: deliberately unfiltered
  const aging = useAgingWip(scope, filters);
  const health = useDeliveryHealth(scope, filters);

  if (metrics.isError || history.isError || distribution.isError) {
    return <Alert type="error" title="Failed to load metrics" />;
  }
  if (metrics.isPending || history.isPending) {
    return <Skeleton active />;
  }

  return (
    <Space direction="vertical" style={{ width: "100%" }} size="large">
      <StaleDataAlert history={history.data} />
      {health.data?.score != null && health.data.band != null && (
        <HealthStrip health={health.data} periodText={periodText(filters, metrics.data)} />
      )}
      <FlowStats
        data={metrics.data}
        statLabel={windowLabel(filters, 30)}
        ranged={isRanged(filters)}
      />
      <FlowCharts
        history={history.data}
        distribution={distribution.data}
        snapshots={snapshots.data}
        chartLabel={windowLabel(filters, 90)}
      />
      {aging.data && aging.data.items.length > 0 && (
        <AgingWipCard items={aging.data.items} percentile={aging.data.percentile} />
      )}
      <ForecastCard scope={scope} filters={filters} />
    </Space>
  );
}
