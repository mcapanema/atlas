import { Alert, Table, Typography } from "antd";

import type { Organization } from "../api/organizations";
import { useOrganizations } from "../api/organizations";
import type { Person } from "../api/people";
import { usePeople, useSetDisplayName } from "../api/people";

const columns = [
  { title: "Name", dataIndex: "name", key: "name" },
  { title: "Created", dataIndex: "created_at", key: "created_at" },
];

function PeopleTable() {
  const { data, isLoading } = usePeople();
  const { mutate, isError, error } = useSetDisplayName();

  return (
    <>
      <Typography.Title level={4}>People</Typography.Title>
      <Typography.Paragraph type="secondary">
        Shown wherever Atlas names an owner. Leave empty to use the name from Linear.
      </Typography.Paragraph>
      {isError && (
        <Alert
          type="error"
          showIcon
          message="Couldn't save the display name"
          description={error.message}
        />
      )}
      <Table<Person>
        rowKey="id"
        loading={isLoading}
        dataSource={data ?? []}
        pagination={false}
        locale={{ emptyText: "People appear after the first sync." }}
        columns={[
          { title: "Name", dataIndex: "name", key: "name" },
          {
            title: "Email",
            dataIndex: "email",
            key: "email",
            render: (email: string | null) => email ?? "—",
          },
          {
            title: "Display name",
            dataIndex: "display_name",
            key: "display_name",
            render: (value: string | null, person) => (
              <Typography.Text
                editable={{
                  text: value ?? "",
                  maxLength: 255,
                  onChange: (next) => mutate({ id: person.id, displayName: next.trim() || null }),
                }}
              >
                {value ?? "—"}
              </Typography.Text>
            ),
          },
        ]}
      />
    </>
  );
}

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
      <PeopleTable />
    </>
  );
}
