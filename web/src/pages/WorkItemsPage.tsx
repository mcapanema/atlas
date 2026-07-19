import { Alert, Select, Space, Table, Tag, Typography } from "antd";
import { Link, useSearchParams } from "react-router-dom";

import { useTeams } from "../api/teams";
import { useWorkItems, WORK_ITEMS_PAGE_SIZE, type WorkItem } from "../api/workItems";
import { formatDateTime } from "../lib/dates";

export function WorkItemsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const teamId = searchParams.get("team") ?? undefined;
  const page = Math.max(1, Number(searchParams.get("page")) || 1);
  const teams = useTeams();
  const workItems = useWorkItems(teamId, page);

  if (teams.isError) {
    return <Alert type="error" message="Failed to load teams" />;
  }
  if (workItems.isError) {
    return <Alert type="error" message="Failed to load work items" />;
  }

  return (
    <>
      <Typography.Title level={3}>Work Items</Typography.Title>
      <Space direction="vertical" style={{ width: "100%" }}>
        <Select
          style={{ width: 260 }}
          placeholder="All teams"
          allowClear
          value={teamId}
          onChange={(value) => setSearchParams(value ? { team: value } : {})}
          options={(teams.data ?? []).map((team) => ({ value: team.id, label: team.name }))}
        />
        <Table
          rowKey="id"
          loading={workItems.isLoading}
          dataSource={workItems.data?.items ?? []}
          pagination={{
            current: page,
            pageSize: WORK_ITEMS_PAGE_SIZE,
            total: workItems.data?.total ?? 0,
            onChange: (nextPage) =>
              setSearchParams((prev) => {
                const next = new URLSearchParams(prev);
                next.set("page", String(nextPage));
                return next;
              }),
            showSizeChanger: false,
          }}
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
              render: (createdAt: string) => formatDateTime(createdAt),
            },
          ]}
        />
      </Space>
    </>
  );
}
