import { Alert, Flex, Select, Space, Tag, Typography } from "antd";
import { useMemo } from "react";
import { useSearchParams } from "react-router-dom";

import { useProjects, type Project } from "../api/projects";
import { useTeams, type Team } from "../api/teams";
import { CustomRulesTag } from "../components/CustomRulesTag";
import { FlowDashboard } from "../components/FlowDashboard";
import { MetricsFilterBar } from "../components/MetricsFilterBar";
import { applyFiltersToSearchParams, filtersFromSearchParams } from "../lib/metricsFilters";
import type { MetricsFilters } from "../api/metrics";

/** Project options grouped under their home team; a multi-team project says how many. */
function projectOptions(projects: Project[], teams: Team[]) {
  const groups = new Map<string, { label: string; options: { value: string; label: string }[] }>();
  for (const p of projects) {
    const label = p.team_ids.length > 1 ? `${p.name} · ${p.team_ids.length} teams` : p.name;
    const group = groups.get(p.team_id) ?? {
      label: teams.find((t) => t.id === p.team_id)?.name ?? "Unknown team",
      options: [],
    };
    group.options.push({ value: p.id, label });
    groups.set(p.team_id, group);
  }
  return [...groups.values()];
}

function RulesTag({ project, teams }: { project: Project | undefined; teams: Team[] }) {
  if (project && project.team_ids.length > 1) return <Tag>Workspace rules</Tag>;
  return <CustomRulesTag team={teams.find((team) => team.id === project?.team_ids[0])} />;
}

export function ProjectDashboardPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const projectId = searchParams.get("project") ?? undefined;
  const filters = useMemo(() => filtersFromSearchParams(searchParams), [searchParams]);
  const projects = useProjects();
  const teams = useTeams();
  const project = projects.data?.find((p) => p.id === projectId);

  const setFilters = (next: MetricsFilters) => {
    const params = new URLSearchParams(searchParams);
    applyFiltersToSearchParams(params, next);
    setSearchParams(params);
  };

  if (projects.isError) {
    return <Alert type="error" message="Failed to load projects" />;
  }
  return (
    <>
      <Typography.Title level={3}>Project Dashboard</Typography.Title>
      <Space direction="vertical" style={{ width: "100%" }} size="large">
        <Flex wrap gap="small" align="center">
          <Select
            aria-label="Project"
            style={{ width: 260 }}
            placeholder="Select a project"
            value={projectId}
            onChange={(value) => {
              const params = new URLSearchParams(searchParams);
              params.set("project", value);
              setSearchParams(params);
            }}
            loading={projects.isLoading}
            options={projectOptions(projects.data ?? [], teams.data ?? [])}
          />
          <RulesTag project={project} teams={teams.data ?? []} />
          {projectId && (
            <MetricsFilterBar filters={filters} scope={{ projectId }} onChange={setFilters} />
          )}
        </Flex>
        {!projectId && <Alert type="info" message="Select a project to see its dashboard." />}
        {projectId && <FlowDashboard scope={{ projectId }} filters={filters} />}
      </Space>
    </>
  );
}
