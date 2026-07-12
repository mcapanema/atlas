import { Alert, Card, Col, Row, Skeleton, Table, Tag } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useMemo } from "react";

import {
  useAgingWip,
  useFlowHistory,
  useFlowMetrics,
  useLeadTimeDistribution,
  type AgingItem,
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
import { formatSeconds } from "../lib/duration";
import { EChart } from "./EChart";
import { ForecastCard } from "./ForecastCard";
import { StatCard } from "./StatCard";

const agingColumns: ColumnsType<AgingItem> = [
  { title: "Title", dataIndex: "title" },
  { title: "State", dataIndex: "state" },
  { title: "Age", render: (_, item) => formatSeconds(item.age_seconds) },
  {
    title: "",
    render: (_, item) => (item.over_p85 ? <Tag color="red">over P85</Tag> : null),
  },
];

function duration(stats: DurationStats | null, key: keyof DurationStats): string {
  return stats ? formatSeconds(stats[key]) : "—";
}

export function FlowDashboard({ scope }: { scope: MetricsScope }) {
  const metrics = useFlowMetrics(scope);
  const history = useFlowHistory(scope);
  const distribution = useLeadTimeDistribution(scope);
  const snapshots = useMetricSnapshots(scope);
  const aging = useAgingWip(scope);

  const cfdOption = useMemo(
    () => (history.data ? buildCfdOption(history.data.days) : null),
    [history.data],
  );
  const throughputOption = useMemo(
    () => (history.data ? buildThroughputOption(history.data.weeks) : null),
    [history.data],
  );
  const wipOption = useMemo(
    () => (history.data ? buildWipOption(history.data.days) : null),
    [history.data],
  );
  const distributionOption = useMemo(
    () => (distribution.data ? buildLeadTimeDistributionOption(distribution.data.bins) : null),
    [distribution.data],
  );
  const trendOption = useMemo(
    () =>
      snapshots.data && snapshots.data.length > 0
        ? buildLeadTimeTrendOption(snapshots.data)
        : null,
    [snapshots.data],
  );

  if (metrics.isError || history.isError || distribution.isError) {
    return <Alert type="error" message="Failed to load metrics" />;
  }
  if (metrics.isPending || history.isPending) {
    return <Skeleton active />;
  }

  const data = metrics.data;
  return (
    <>
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
    </>
  );
}
