import { Alert, Button, Card, Descriptions, Select, Space, Tag, Typography } from "antd";
import { useState } from "react";

import { useLinearStatus, useLinearSync, type SyncSummary } from "../api/connectors";
import { useOrganizations } from "../api/organizations";

function SyncSummaryTable({ summary }: { summary: SyncSummary }) {
  return (
    <Descriptions column={6} bordered size="small">
      <Descriptions.Item label="Teams">{summary.teams}</Descriptions.Item>
      <Descriptions.Item label="Projects">{summary.projects}</Descriptions.Item>
      <Descriptions.Item label="Work items">{summary.work_items}</Descriptions.Item>
      <Descriptions.Item label="Events">{summary.events}</Descriptions.Item>
      <Descriptions.Item label="Divergences">{summary.divergences}</Descriptions.Item>
      <Descriptions.Item label="Deleted">{summary.deleted}</Descriptions.Item>
    </Descriptions>
  );
}

function SetupHints({
  configured,
  noOrganizations,
}: {
  configured: boolean;
  noOrganizations: boolean;
}) {
  return (
    <>
      {!configured && (
        <Alert
          type="info"
          message="Set ATLAS_LINEAR_API_KEY (a Linear personal API key) in the server environment, then restart Atlas."
        />
      )}
      {noOrganizations && (
        <Alert
          type="info"
          message="No organization yet — the first sync will create one from your Linear workspace."
        />
      )}
    </>
  );
}

function SyncOutcome({ sync }: { sync: ReturnType<typeof useLinearSync> }) {
  if (sync.isError) {
    return <Alert type="error" message="Sync failed" description={sync.error.message} />;
  }
  return sync.data ? <SyncSummaryTable summary={sync.data} /> : null;
}

export function ConnectorsPage() {
  const status = useLinearStatus();
  const organizations = useOrganizations();
  const sync = useLinearSync();
  const [organizationId, setOrganizationId] = useState<string>();

  const orgList = organizations.data ?? [];
  // Default to the first organization once loaded; the Select can override.
  const selectedOrgId = organizationId ?? orgList[0]?.id;
  const configured = status.data?.configured ?? false;
  const loadError = status.error ?? organizations.error;

  if (loadError) {
    return (
      <>
        <Typography.Title level={3}>Connectors</Typography.Title>
        <Alert
          type="error"
          message="Failed to load connector status"
          description={loadError.message}
        />
      </>
    );
  }
  return (
    <>
      <Typography.Title level={3}>Connectors</Typography.Title>
      <Card
        title="Linear"
        loading={status.isLoading || organizations.isLoading}
        extra={configured ? <Tag color="green">Configured</Tag> : <Tag>Not configured</Tag>}
      >
        <Space direction="vertical" style={{ width: "100%" }}>
          <SetupHints
            configured={configured}
            noOrganizations={configured && !organizations.isLoading && orgList.length === 0}
          />
          <Space>
            <Select
              style={{ width: 260 }}
              placeholder="Organization"
              value={selectedOrgId}
              onChange={setOrganizationId}
              options={orgList.map((org) => ({ value: org.id, label: org.name }))}
            />
            <Button
              type="primary"
              disabled={!configured}
              loading={sync.isPending}
              onClick={() => sync.mutate(selectedOrgId)}
            >
              Sync now
            </Button>
          </Space>
          <SyncOutcome sync={sync} />
        </Space>
      </Card>
    </>
  );
}
