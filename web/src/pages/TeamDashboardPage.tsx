import { Alert, Select, Space, Typography } from "antd";
import { useSearchParams } from "react-router-dom";

import { useTeams } from "../api/teams";
import { FlowDashboard } from "../components/FlowDashboard";

export function TeamDashboardPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const teamId = searchParams.get("team") ?? undefined;
  const teams = useTeams();

  if (teams.isError) {
    return <Alert type="error" message="Failed to load teams" />;
  }
  return (
    <>
      <Typography.Title level={3}>Team Dashboard</Typography.Title>
      <Space direction="vertical" style={{ width: "100%" }} size="large">
        <Select
          style={{ width: 260 }}
          placeholder="Select a team"
          value={teamId}
          onChange={(value) => setSearchParams({ team: value })}
          loading={teams.isLoading}
          options={(teams.data ?? []).map((team) => ({ value: team.id, label: team.name }))}
        />
        {!teamId && <Alert type="info" message="Select a team to see its dashboard." />}
        {teamId && <FlowDashboard scope={{ teamId }} />}
      </Space>
    </>
  );
}
