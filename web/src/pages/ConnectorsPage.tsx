import { Alert, Button, Card, Descriptions, Select, Space, Tag, Typography } from "antd";
import { useState } from "react";

import { useLinearStatus, useLinearSync } from "../api/connectors";
import { useOrganizations } from "../api/organizations";

export function ConnectorsPage() {
  const status = useLinearStatus();
  const organizations = useOrganizations();
  const sync = useLinearSync();
  const [organizationId, setOrganizationId] = useState<string>();

  // Default to the first organization once loaded; the Select can override.
  const selectedOrgId = organizationId ?? organizations.data?.[0]?.id;
  const configured = status.data?.configured ?? false;
  const loadError = status.error ?? organizations.error;

  return (
    <>
      <Typography.Title level={3}>Connectors</Typography.Title>
      {loadError ? (
        <Alert
          type="error"
          message="Failed to load connector status"
          description={loadError.message}
        />
      ) : (
        <Card
          title="Linear"
          loading={status.isLoading || organizations.isLoading}
          extra={configured ? <Tag color="green">Configured</Tag> : <Tag>Not configured</Tag>}
        >
          <Space direction="vertical" style={{ width: "100%" }}>
            {!configured && (
              <Alert
                type="info"
                message="Set ATLAS_LINEAR_API_KEY (a Linear personal API key) in the server environment, then restart Atlas."
              />
            )}
            <Space>
              <Select
                style={{ width: 260 }}
                placeholder="Organization"
                value={selectedOrgId}
                onChange={setOrganizationId}
                options={(organizations.data ?? []).map((org) => ({
                  value: org.id,
                  label: org.name,
                }))}
              />
              <Button
                type="primary"
                disabled={!configured || !selectedOrgId}
                loading={sync.isPending}
                onClick={() => selectedOrgId && sync.mutate(selectedOrgId)}
              >
                Sync now
              </Button>
            </Space>
            {sync.isError && (
              <Alert type="error" message="Sync failed" description={sync.error.message} />
            )}
            {sync.data && (
              <Descriptions column={5} bordered size="small">
                <Descriptions.Item label="Teams">{sync.data.teams}</Descriptions.Item>
                <Descriptions.Item label="Projects">{sync.data.projects}</Descriptions.Item>
                <Descriptions.Item label="Work items">{sync.data.work_items}</Descriptions.Item>
                <Descriptions.Item label="Events">{sync.data.events}</Descriptions.Item>
                <Descriptions.Item label="Divergences">
                  {sync.data.divergences}
                </Descriptions.Item>
              </Descriptions>
            )}
          </Space>
        </Card>
      )}
    </>
  );
}
