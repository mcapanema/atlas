import { Alert, Select, Space, Typography, theme } from "antd";
import { useMemo } from "react";
import { useSearchParams } from "react-router-dom";

import { useTeams } from "../api/teams";
import { CustomRulesTag } from "../components/CustomRulesTag";
import { FlowDashboard } from "../components/FlowDashboard";
import { MetricsFilterBar } from "../components/MetricsFilterBar";
import { TeamSyncButton } from "../components/TeamSyncButton";
import { applyFiltersToSearchParams, filtersFromSearchParams } from "../lib/metricsFilters";
import type { MetricsFilters } from "../api/metrics";

export function TeamDashboardPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const teamId = searchParams.get("team") ?? undefined;
  const filters = useMemo(() => filtersFromSearchParams(searchParams), [searchParams]);
  const teams = useTeams();
  const team = teams.data?.find((candidate) => candidate.id === teamId);
  const { token } = theme.useToken();

  const setFilters = (next: MetricsFilters) => {
    const params = new URLSearchParams(searchParams);
    applyFiltersToSearchParams(params, next);
    setSearchParams(params);
  };

  if (teams.isError) {
    return <Alert type="error" message="Failed to load teams" />;
  }
  return (
    <>
      <Typography.Title level={3}>Team Dashboard</Typography.Title>
      {teamId && (team || teams.isLoading) && (
        // Held at the button's height while a deep-linked team loads, so the
        // selector doesn't jump down when it arrives.
        <div style={{ marginBottom: 12, minHeight: token.controlHeight }}>
          {/* Keyed: one team's sync result must not carry over to the next. */}
          {team && <TeamSyncButton key={team.id} team={team} />}
        </div>
      )}
      <Space direction="vertical" style={{ width: "100%" }} size="large">
        <Space wrap>
          <Select
            style={{ width: 260 }}
            placeholder="Select a team"
            value={teamId}
            onChange={(value) => {
              const params = new URLSearchParams(searchParams);
              params.set("team", value);
              setSearchParams(params);
            }}
            loading={teams.isLoading}
            options={(teams.data ?? []).map((team) => ({ value: team.id, label: team.name }))}
          />
          <CustomRulesTag team={team} />
          {teamId && (
            <MetricsFilterBar filters={filters} scope={{ teamId }} onChange={setFilters} />
          )}
        </Space>
        {!teamId && <Alert type="info" message="Select a team to see its dashboard." />}
        {teamId && <FlowDashboard scope={{ teamId }} filters={filters} />}
      </Space>
    </>
  );
}
