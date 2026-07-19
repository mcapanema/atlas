import { Alert, Card, Col, Row, Skeleton, Space, Table, Tag } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useMemo } from "react";
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
  type MetricsFilters,
  type MetricsScope,
} from "../api/metrics";
import { useMetricSnapshots } from "../api/snapshots";
import {
  buildCfdOption,
  buildLeadTimeDistributionOption,
  buildLeadTimeTrendOption,
  buildThroughputOption,
  buildWipOption,
  throughputTitle,
} from "../lib/charts";
import { formatDateTime, formatDay } from "../lib/dates";
import { formatSeconds } from "../lib/duration";
import { STALE_AFTER_HOURS, stalenessHours } from "../lib/freshness";
import { windowLabel } from "../lib/metricsFilters";
import { useThemeMode } from "../theme/context";
import { EChart } from "./EChart";
import { ForecastCard } from "./ForecastCard";
import { HealthBadge } from "./HealthBadge";
import { HelpLabel } from "./HelpLabel";
import { StatCard } from "./StatCard";

const agingColumns: ColumnsType<AgingItem> = [
  {
    title: "Title",
    dataIndex: "title",
    render: (title, item) => <Link to={`/work-items/${item.work_item_id}`}>{title}</Link>,
  },
  { title: "State", dataIndex: "state" },
  { title: "Age", className: "fig", render: (_, item) => formatSeconds(item.age_seconds) },
  {
    title: "",
    render: (_, item) => (item.over_p85 ? <Tag color="red">over P85</Tag> : null),
  },
];

function duration(stats: DurationStats | null, key: keyof DurationStats): string {
  return stats ? formatSeconds(stats[key]) : "—";
}

/**
 * Health leads the page — same vocabulary as the executive dashboard:
 * quiet badge + window when healthy, tinted attention card with the two
 * weakest component reasons when at risk.
 */
function HealthStrip({
  health,
  periodText,
}: {
  health: DeliveryHealth;
  periodText: string | null;
}) {
  const atRisk = health.band === "critical" || health.band === "warning";
  const reasons = atRisk
    ? [...health.components].sort((a, b) => a.score - b.score).slice(0, 2)
    : [];
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
  const { mode } = useThemeMode();

  const cfdOption = useMemo(
    () => (history.data ? buildCfdOption(history.data.days, mode) : null),
    [history.data, mode],
  );
  const throughputOption = useMemo(
    // ponytail: one bucket is not a trend — it restates the Throughput stat
    // tile as a single bar. Short windows now bucket daily upstream, so this
    // guard is a safety net rather than the common path.
    () =>
      history.data && history.data.buckets.length > 1
        ? buildThroughputOption(history.data.buckets, history.data.bucket_days, mode)
        : null,
    [history.data, mode],
  );
  const wipOption = useMemo(
    () => (history.data ? buildWipOption(history.data.days, mode) : null),
    [history.data, mode],
  );
  const distributionOption = useMemo(
    () =>
      distribution.data ? buildLeadTimeDistributionOption(distribution.data.bins, mode) : null,
    [distribution.data, mode],
  );
  const trendOption = useMemo(
    () =>
      snapshots.data && snapshots.data.length > 0
        ? buildLeadTimeTrendOption(snapshots.data, mode)
        : null,
    [snapshots.data, mode],
  );

  if (metrics.isError || history.isError || distribution.isError) {
    return <Alert type="error" message="Failed to load metrics" />;
  }
  if (metrics.isPending || history.isPending) {
    return <Skeleton active />;
  }

  const data = metrics.data;
  const statLabel = windowLabel(filters, 30);
  const chartLabel = windowLabel(filters, 90);
  const periodText =
    filters.start && filters.end
      ? `${formatDay(filters.start)} – ${formatDay(filters.end)}`
      : data
        ? `Last ${filters.windowDays ?? 30} days · ${formatDay(data.window_start)} – ${formatDay(data.window_end)}`
        : null;
  const staleHours = history.data
    ? stalenessHours(history.data.data_as_of, history.data.window_end)
    : null;
  const staleDays = staleHours === null ? 0 : Math.floor(staleHours / 24);
  return (
    <Space direction="vertical" style={{ width: "100%" }} size="large">
      {history.data?.data_as_of && staleHours !== null && staleHours > STALE_AFTER_HOURS && (
        <Alert
          type="warning"
          showIcon
          message={`Data last synced ${formatDateTime(history.data.data_as_of)}`}
          description={`The last ${staleDays} day${staleDays === 1 ? "" : "s"} of this window have no synced data. Charts show zero for that period because nothing has been ingested, not because nothing was delivered.`}
        />
      )}
      {health.data && health.data.score != null && health.data.band != null && (
        <HealthStrip health={health.data} periodText={periodText} />
      )}
      {data && (
        <Row gutter={[16, 16]}>
          <StatCard
            title={`Throughput (${statLabel})`}
            value={data.completed}
            help={`Work items completed in the last ${statLabel}. Counted at the moment an item reached a done state.`}
          />
          <StatCard
            title="WIP (now)"
            value={data.wip}
            help="Work items started but not yet completed, right now. Not an average over the window."
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
            title={`Blocked time (${statLabel})`}
            value={formatSeconds(data.blocked_seconds)}
            help={`Total time items spent carrying a blocked label in the last ${statLabel}, summed across all items.`}
          />
          <StatCard
            title="Flow efficiency"
            value={
              data.flow_efficiency != null ? `${Math.round(data.flow_efficiency * 100)}%` : "—"
            }
            help="Touch time divided by lead time. The share of an item's life that was active work rather than waiting."
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
        </Row>
      )}
      {cfdOption && wipOption && (
        <Row gutter={[16, 16]}>
          <Col xs={24}>
            <Card
              title={
                <HelpLabel
                  label={`Cumulative flow (${chartLabel})`}
                  help="How many items sat in each state on each day of the window. Widening bands mean work arriving faster than it leaves."
                />
              }
            >
              <EChart option={cfdOption} height={300} />
            </Card>
          </Col>
          {throughputOption && history.data && (
            <Col xs={24} lg={12}>
              <Card
                title={
                  <HelpLabel
                    label={throughputTitle(history.data.bucket_days, chartLabel)}
                    help={
                      history.data.bucket_days === 1
                        ? "Work items completed on each day of the window. Windows of 21 days or fewer bucket per day."
                        : "Work items completed in each trailing 7-day bucket, oldest first. Longer windows bucket per week to keep the shape readable."
                    }
                  />
                }
              >
                <EChart option={throughputOption} />
              </Card>
            </Col>
          )}
          <Col xs={24} lg={12}>
            <Card
              title={
                <HelpLabel
                  label={`WIP over time (${chartLabel})`}
                  help="Items in progress at the end of each day. A rising line means work is being started faster than it is finished."
                />
              }
            >
              <EChart option={wipOption} />
            </Card>
          </Col>
          {distributionOption && (
            <Col xs={24} lg={12}>
              <Card
                title={
                  <HelpLabel
                    label={`Lead time distribution (${chartLabel})`}
                    help="How many completed items fell into each lead-time bucket. A long right tail means a few items took far longer than typical."
                  />
                }
              >
                <EChart option={distributionOption} />
              </Card>
            </Col>
          )}
          {trendOption && (
            <Col xs={24} lg={12}>
              <Card
                title={
                  <HelpLabel
                    label="Lead time trend"
                    help="Daily snapshots of lead time P50 and P85. Always the unfiltered 30-day baseline, so it does not follow the filters above."
                  />
                }
              >
                <EChart option={trendOption} />
              </Card>
            </Col>
          )}
        </Row>
      )}
      {aging.data && aging.data.items.length > 0 && (
        <Card
          title={
            <HelpLabel
              label="Aging WIP"
              help="Items currently in progress, oldest first. Flagged when they have already been open longer than 85% of completed items took."
            />
          }
        >
          <Table
            size="small"
            rowKey="work_item_id"
            pagination={false}
            columns={agingColumns}
            dataSource={aging.data.items}
          />
        </Card>
      )}
      <ForecastCard scope={scope} />
    </Space>
  );
}
