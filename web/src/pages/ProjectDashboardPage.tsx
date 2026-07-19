import { Alert, Select, Space, Typography } from "antd";
import { useMemo } from "react";
import { useSearchParams } from "react-router-dom";

import { useProjects } from "../api/projects";
import { FlowDashboard } from "../components/FlowDashboard";
import { MetricsFilterBar } from "../components/MetricsFilterBar";
import {
  applyFiltersToSearchParams,
  filtersFromSearchParams,
} from "../lib/metricsFilters";
import type { MetricsFilters } from "../api/metrics";

export function ProjectDashboardPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const projectId = searchParams.get("project") ?? undefined;
  const filters = useMemo(() => filtersFromSearchParams(searchParams), [searchParams]);
  const projects = useProjects();

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
        <Space wrap>
          <Select
            style={{ width: 260 }}
            placeholder="Select a project"
            value={projectId}
            onChange={(value) => {
              const params = new URLSearchParams(searchParams);
              params.set("project", value);
              setSearchParams(params);
            }}
            loading={projects.isLoading}
            options={(projects.data ?? []).map((p) => ({ value: p.id, label: p.name }))}
          />
          {projectId && (
            <MetricsFilterBar
              filters={filters}
              scope={{ projectId }}
              onChange={setFilters}
            />
          )}
        </Space>
        {!projectId && <Alert type="info" message="Select a project to see its dashboard." />}
        {projectId && <FlowDashboard scope={{ projectId }} filters={filters} />}
      </Space>
    </>
  );
}
