import { Alert, Select, Space, Typography } from "antd";
import { useSearchParams } from "react-router-dom";

import { useProjects } from "../api/projects";
import { FlowDashboard } from "../components/FlowDashboard";

export function ProjectDashboardPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const projectId = searchParams.get("project") ?? undefined;
  const projects = useProjects();

  if (projects.isError) {
    return <Alert type="error" message="Failed to load projects" />;
  }
  return (
    <>
      <Typography.Title level={3}>Project Dashboard</Typography.Title>
      <Space direction="vertical" style={{ width: "100%" }} size="large">
        <Select
          style={{ width: 260 }}
          placeholder="Select a project"
          value={projectId}
          onChange={(value) => setSearchParams({ project: value })}
          loading={projects.isLoading}
          options={(projects.data ?? []).map((p) => ({ value: p.id, label: p.name }))}
        />
        {!projectId && <Alert type="info" message="Select a project to see its dashboard." />}
        {projectId && <FlowDashboard scope={{ projectId }} />}
      </Space>
    </>
  );
}
