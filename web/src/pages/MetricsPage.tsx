import { Alert, Card, Col, Row, Select, Space, Statistic, Typography } from "antd";
import { useState } from "react";

import { useTeamFlowMetrics, type DurationStats } from "../api/metrics";
import { useTeams } from "../api/teams";
import { formatSeconds } from "../lib/duration";

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

export function MetricsPage() {
  const [teamId, setTeamId] = useState<string>();
  const teams = useTeams();
  const metrics = useTeamFlowMetrics(teamId);

  if (teams.isError) {
    return <Alert type="error" message="Failed to load teams" />;
  }
  if (metrics.isError) {
    return <Alert type="error" message="Failed to load metrics" />;
  }

  const data = metrics.data;
  return (
    <>
      <Typography.Title level={3}>Flow Metrics</Typography.Title>
      <Space direction="vertical" style={{ width: "100%" }} size="large">
        <Select
          style={{ width: 260 }}
          placeholder="Select a team"
          value={teamId}
          onChange={setTeamId}
          loading={teams.isLoading}
          options={(teams.data ?? []).map((team) => ({ value: team.id, label: team.name }))}
        />
        {!teamId && (
          <Alert type="info" message="Select a team to see its flow metrics (last 30 days)." />
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
                data.flow_efficiency != null
                  ? `${Math.round(data.flow_efficiency * 100)}%`
                  : "—"
              }
            />
          </Row>
        )}
      </Space>
    </>
  );
}
