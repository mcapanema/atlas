import { SyncOutlined } from "@ant-design/icons";
import { Alert, Badge, Button, Card, Flex, Select, Typography } from "antd";
import { useState } from "react";

import { useLinearStatus, useLinearSync, type ConnectorStatus } from "../api/connectors";
import { useOrganizations, type Organization } from "../api/organizations";
import { AutoSyncCard } from "../components/AutoSyncCard";
import { SyncStatus } from "../components/SyncStatus";
import { syncOutcome } from "../lib/syncOutcome";

function SetupAlert() {
  return (
    <Alert
      type="warning"
      showIcon
      title="Linear isn't configured"
      description={
        <>
          Set <Typography.Text code>ATLAS_LINEAR_API_KEY</Typography.Text> (a Linear personal API
          key) in the server environment, then restart Atlas. Until then Sync now is off and
          scheduled syncs fail.
        </>
      }
    />
  );
}

function OrganizationPicker({
  organizations,
  value,
  onChange,
  canBootstrap,
}: {
  organizations: Organization[];
  value: string | undefined;
  onChange: (organizationId: string) => void;
  canBootstrap: boolean;
}) {
  if (organizations.length > 0) {
    return (
      <Select
        aria-label="Organization"
        style={{ width: 260 }}
        value={value}
        onChange={onChange}
        options={organizations.map((org) => ({ value: org.id, label: org.name }))}
      />
    );
  }
  return canBootstrap ? (
    <Alert
      type="info"
      showIcon
      title="No organization yet — the first sync will create one from your Linear workspace."
    />
  ) : null;
}

type LinearSync = ReturnType<typeof useLinearSync>;

/** Manual sync, matching the Team Dashboard's Sync team: icon, inline wait hint and outcome. */
function SyncNow({
  sync,
  organizationId,
  configured,
  autoSyncing,
}: {
  sync: LinearSync;
  organizationId: string | undefined;
  configured: boolean;
  autoSyncing: boolean;
}) {
  return (
    <Flex vertical gap="small">
      <Flex wrap gap="small" align="center">
        <Button
          type="primary"
          icon={<SyncOutlined />}
          disabled={!configured}
          loading={sync.isPending}
          onClick={() => sync.mutate(organizationId)}
        >
          Sync now
        </Button>
        {autoSyncing && (
          <Typography.Text type="secondary">
            An automatic sync is running; Sync now starts when it finishes.
          </Typography.Text>
        )}
        {sync.data && <Typography.Text type="secondary">{syncOutcome(sync.data)}</Typography.Text>}
      </Flex>
      {sync.isError && (
        <Alert type="error" showIcon title="Sync failed" description={sync.error.message} />
      )}
    </Flex>
  );
}

function LinearCard({
  status,
  sync,
  organizationId,
  loading,
}: {
  status: ConnectorStatus | undefined;
  sync: LinearSync;
  organizationId: string | undefined;
  loading: boolean;
}) {
  const configured = status?.configured ?? false;
  // A dot plus a word: the state never rides on color alone.
  const badge = configured ? (
    <Badge status="success" text="Configured" />
  ) : (
    <Badge status="default" text="Not configured" />
  );
  return (
    <Card title="Linear" loading={loading} extra={loading ? null : badge}>
      <Flex vertical gap="middle">
        {organizationId && <SyncStatus organizationId={organizationId} />}
        <SyncNow
          sync={sync}
          organizationId={organizationId}
          configured={configured}
          autoSyncing={status?.auto_syncing ?? false}
        />
      </Flex>
    </Card>
  );
}

function ConnectorsWorkspace({
  status,
  organizations,
}: {
  status: ReturnType<typeof useLinearStatus>;
  organizations: ReturnType<typeof useOrganizations>;
}) {
  const [organizationId, setOrganizationId] = useState<string>();
  // Owned here, not in SyncNow, so picking another organization can clear
  // the last outcome; a first sync that creates the organization keeps it.
  const sync = useLinearSync();
  const pickOrganization = (id: string) => {
    sync.reset();
    setOrganizationId(id);
  };
  const orgList = organizations.data ?? [];
  // Default to the first organization once loaded; the picker can override.
  const selectedOrgId = organizationId ?? orgList[0]?.id;
  const configured = status.data?.configured;
  const loading = status.isLoading || organizations.isLoading;
  return (
    <Flex vertical gap="middle">
      {configured === false && <SetupAlert />}
      {!loading && (
        <OrganizationPicker
          organizations={orgList}
          value={selectedOrgId}
          onChange={pickOrganization}
          canBootstrap={configured === true}
        />
      )}
      <LinearCard
        status={status.data}
        sync={sync}
        organizationId={selectedOrgId}
        loading={loading}
      />
      {selectedOrgId && (
        // Keyed: another organization's save result must not carry over.
        <AutoSyncCard key={selectedOrgId} organizationId={selectedOrgId} />
      )}
    </Flex>
  );
}

export function ConnectorsPage() {
  const status = useLinearStatus();
  const organizations = useOrganizations();
  const loadError = status.error ?? organizations.error;
  return (
    <div className="page-settings">
      <Typography.Title level={3}>Connectors</Typography.Title>
      <Typography.Paragraph type="secondary">
        Where Atlas gets its delivery data. Sync now pulls the latest from Linear; auto sync keeps
        it fresh on a schedule.
      </Typography.Paragraph>
      {loadError ? (
        <Alert
          type="error"
          showIcon
          title="Failed to load connector status"
          description={loadError.message}
        />
      ) : (
        <ConnectorsWorkspace status={status} organizations={organizations} />
      )}
    </div>
  );
}
