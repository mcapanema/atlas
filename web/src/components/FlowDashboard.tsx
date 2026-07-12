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
  type MetricsScope,
} from "../api/metrics";
import { useMetricSnapshots } from "../api/snapshots";
import {
  buildCfdOption,
  buildLeadTimeDistributionOption,
  buildLeadTimeTrendOption,
  buildThroughputOption,
  buildWipOption,
} from "../lib/charts";
import { formatDay } from "../lib/dates";
import { formatSeconds } from "../lib/duration";
import { useThemeMode } from "../theme/context";
import { EChart } from "./EChart";
import { ForecastCard } from "./ForecastCard";
import { HealthBadge } from "./HealthBadge";
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
  window: metricsWindow,
}: {
  health: DeliveryHealth;
  window: { start: string; end: string } | null;
}) {
  const atRisk = health.band === "critical" || health.band === "warning";
  const reasons = atRisk
    ? [...health.components].sort((a, b) => a.score - b.score).slice(0, 2)
    : [];
  return (
    <section aria-label="Delivery health" className="health-strip">
      <div className="health-strip__row">
        <HealthBadge health={health} />
        {metricsWindow && (
          <span className="page-asof">
            Last 30 days · {formatDay(metricsWindow.start)} – {formatDay(metricsWindow.end)}
          </span>
        )}
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

export function FlowDashboard({ scope }: { scope: MetricsScope }) {
  const metrics = useFlowMetrics(scope);
  const history = useFlowHistory(scope);
  const distribution = useLeadTimeDistribution(scope);
  const snapshots = useMetricSnapshots(scope);
  const aging = useAgingWip(scope);
  const health = useDeliveryHealth(scope);
  const { mode } = useThemeMode();

  const cfdOption = useMemo(
    () => (history.data ? buildCfdOption(history.data.days, mode) : null),
    [history.data, mode],
  );
  const throughputOption = useMemo(
    () => (history.data ? buildThroughputOption(history.data.weeks, mode) : null),
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
  return (
    <Space direction="vertical" style={{ width: "100%" }} size="large">
      {health.data && health.data.score != null && health.data.band != null && (
        <HealthStrip
          health={health.data}
          window={data ? { start: data.window_start, end: data.window_end } : null}
        />
      )}
      {data && (
        <Row gutter={[16, 16]}>
          <StatCard title="Throughput (30d)" value={data.completed} />
          <StatCard title="WIP (now)" value={data.wip} />
          <StatCard title="Lead time P50" value={duration(data.lead_time, "p50_seconds")} />
          <StatCard title="Lead time P85" value={duration(data.lead_time, "p85_seconds")} />
          <StatCard title="Cycle time P50" value={duration(data.cycle_time, "p50_seconds")} />
          <StatCard title="Cycle time P85" value={duration(data.cycle_time, "p85_seconds")} />
          <StatCard title="Blocked time (30d)" value={formatSeconds(data.blocked_seconds)} />
          <StatCard
            title="Flow efficiency"
            value={
              data.flow_efficiency != null ? `${Math.round(data.flow_efficiency * 100)}%` : "—"
            }
          />
          <StatCard title="Queue time P50" value={duration(data.queue_time, "p50_seconds")} />
          <StatCard title="Touch time P50" value={duration(data.touch_time, "p50_seconds")} />
        </Row>
      )}
      {cfdOption && throughputOption && wipOption && (
        <Row gutter={[16, 16]}>
          <Col xs={24}>
            <Card title="Cumulative flow (90d)">
              <EChart option={cfdOption} height={300} />
            </Card>
          </Col>
          <Col xs={24} lg={12}>
            <Card title="Weekly throughput (90d)">
              <EChart option={throughputOption} />
            </Card>
          </Col>
          <Col xs={24} lg={12}>
            <Card title="WIP over time (90d)">
              <EChart option={wipOption} />
            </Card>
          </Col>
          {distributionOption && (
            <Col xs={24} lg={12}>
              <Card title="Lead time distribution (90d)">
                <EChart option={distributionOption} />
              </Card>
            </Col>
          )}
          {trendOption && (
            <Col xs={24} lg={12}>
              <Card title="Lead time trend">
                <EChart option={trendOption} />
              </Card>
            </Col>
          )}
        </Row>
      )}
      {aging.data && aging.data.items.length > 0 && (
        <Card title="Aging WIP">
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
