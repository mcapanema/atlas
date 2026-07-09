import { Alert, Table, Typography } from "antd";

import type { Organization } from "../api/organizations";
import { useOrganizations } from "../api/organizations";

const columns = [
  { title: "Name", dataIndex: "name", key: "name" },
  { title: "Created", dataIndex: "created_at", key: "created_at" },
];

export function OrganizationsPage() {
  const { data, isLoading, isError } = useOrganizations();

  if (isError) {
    return <Alert type="error" message="Failed to load organizations" />;
  }

  return (
    <>
      <Typography.Title level={3}>Organizations</Typography.Title>
      <Table<Organization>
        rowKey="id"
        loading={isLoading}
        dataSource={data ?? []}
        columns={columns}
        pagination={false}
      />
    </>
  );
}
