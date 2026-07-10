import { Alert, Card, Col, Row, Statistic } from "antd";

import {
  useFlowHistory,
  useFlowMetrics,
  type DurationStats,
  type MetricsScope,
} from "../api/metrics";
import { buildCfdOption, buildThroughputOption, buildWipOption } from "../lib/charts";
import { formatSeconds } from "../lib/duration";
import { EChart } from "./EChart";

function duration(stats: DurationStats | null, key: keyof DurationStats): string {
  return stats ? formatSeconds(stats[key]) : "—";
}

function StatCard({ title, value }: { title: string; value: string | number }) {
  return (
    <Col xs={12} lg={6}>
      <Card>
        <Statistic title={title} value={value} />
      </Card>
    </Col>
  );
}

export function FlowDashboard({ scope }: { scope: MetricsScope }) {
  const metrics = useFlowMetrics(scope);
  const history = useFlowHistory(scope);

  if (metrics.isError || history.isError) {
    return <Alert type="error" message="Failed to load metrics" />;
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
        </Row>
      )}
      {history.data && (
        <Row gutter={[16, 16]}>
          <Col xs={24}>
            <Card title="Cumulative flow (90d)">
              <EChart option={buildCfdOption(history.data.days)} height={300} />
            </Card>
          </Col>
          <Col xs={24} lg={12}>
            <Card title="Weekly throughput (90d)">
              <EChart option={buildThroughputOption(history.data.weeks)} />
            </Card>
          </Col>
          <Col xs={24} lg={12}>
            <Card title="WIP over time (90d)">
              <EChart option={buildWipOption(history.data.days)} />
            </Card>
          </Col>
        </Row>
      )}
    </>
  );
}
