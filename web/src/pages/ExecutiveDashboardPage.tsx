import { Alert, Table, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { Link } from "react-router-dom";

import { useAllTeamsFlowMetrics, type FlowMetrics } from "../api/metrics";
import { useAllTeamsForecastAccuracy, type ForecastAccuracy } from "../api/snapshots";
import { useTeams, type Team } from "../api/teams";
import { formatSeconds } from "../lib/duration";

interface TeamRow {
  key: string;
  team: Team;
  metrics: FlowMetrics | undefined;
  accuracy: ForecastAccuracy | undefined;
}

const columns: ColumnsType<TeamRow> = [
  {
    title: "Team",
    render: (_, row) => <Link to={`/teams?team=${row.team.id}`}>{row.team.name}</Link>,
  },
  { title: "Throughput (30d)", render: (_, row) => row.metrics?.completed ?? "—" },
  { title: "WIP", render: (_, row) => row.metrics?.wip ?? "—" },
  {
    title: "Lead time P85",
    render: (_, row) =>
      row.metrics?.lead_time ? formatSeconds(row.metrics.lead_time.p85_seconds) : "—",
  },
  {
    title: "Flow efficiency",
    render: (_, row) =>
      row.metrics?.flow_efficiency != null
        ? `${Math.round(row.metrics.flow_efficiency * 100)}%`
        : "—",
  },
  {
    title: "Blocked (30d)",
    render: (_, row) => (row.metrics ? formatSeconds(row.metrics.blocked_seconds) : "—"),
  },
  {
    title: "Forecast accuracy (P85)",
    render: (_, row) =>
      row.accuracy && row.accuracy.evaluated > 0 && row.accuracy.p85_hit_rate != null
        ? `${Math.round(row.accuracy.p85_hit_rate * 100)}%`
        : "—",
  },
];

export function ExecutiveDashboardPage() {
  const teams = useTeams();
  // ponytail: one /api/metrics call per team; add a portfolio endpoint when
  // team count makes N round trips slow.
  const metrics = useAllTeamsFlowMetrics(teams.data ?? []);
  const accuracy = useAllTeamsForecastAccuracy(teams.data ?? []);

  if (teams.isError) {
    return <Alert type="error" message="Failed to load teams" />;
  }
  const rows: TeamRow[] = (teams.data ?? []).map((team, index) => ({
    key: team.id,
    team,
    metrics: metrics[index]?.data,
    accuracy: accuracy[index]?.data,
  }));
  const failedCount = metrics.filter((m) => m.isError).length;
  return (
    <>
      <Typography.Title level={3}>Executive Dashboard</Typography.Title>
      {failedCount > 0 && (
        <Alert
          type="warning"
          style={{ marginBottom: 16 }}
          message={`Metrics failed to load for ${failedCount} team${failedCount === 1 ? "" : "s"}`}
        />
      )}
      <Table columns={columns} dataSource={rows} loading={teams.isLoading} pagination={false} />
    </>
  );
}
