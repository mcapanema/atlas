import { Select, Space, Table, Tag, Typography } from "antd";
import { useState } from "react";
import { Link } from "react-router-dom";

import { useTeams } from "../api/teams";
import { useWorkItems, type WorkItem } from "../api/workItems";

export function WorkItemsPage() {
  const [teamId, setTeamId] = useState<string>();
  const teams = useTeams();
  const workItems = useWorkItems(teamId);

  return (
    <>
      <Typography.Title level={3}>Work Items</Typography.Title>
      <Space direction="vertical" style={{ width: "100%" }}>
        <Select
          style={{ width: 260 }}
          placeholder="All teams"
          allowClear
          value={teamId}
          onChange={setTeamId}
          options={(teams.data ?? []).map((team) => ({ value: team.id, label: team.name }))}
        />
        <Table
          rowKey="id"
          loading={workItems.isLoading}
          dataSource={workItems.data ?? []}
          columns={[
            {
              title: "Title",
              dataIndex: "title",
              render: (title: string, item: WorkItem) => (
                <Link to={`/work-items/${item.id}`}>{title}</Link>
              ),
            },
            {
              title: "Type",
              dataIndex: "type",
              render: (type: string) => <Tag>{type}</Tag>,
            },
            {
              title: "State",
              dataIndex: "state",
              render: (state: string) => <Tag color="blue">{state}</Tag>,
            },
            {
              title: "Created",
              dataIndex: "created_at",
              render: (createdAt: string) => new Date(createdAt).toLocaleString(),
            },
          ]}
        />
      </Space>
    </>
  );
}
