import { SyncOutlined } from "@ant-design/icons";
import { Alert, Badge, Button, Card, Flex, Typography } from "antd";

import { useDatadogStatus, useDatadogSync, type DatadogStatus } from "../api/connectors";
import { datadogSyncOutcome } from "../lib/syncOutcome";
import { CodebasesTable } from "./CodebasesTable";
import { CredentialsSection } from "./CredentialsSection";

const SITES = [
  "datadoghq.com",
  "us3.datadoghq.com",
  "us5.datadoghq.com",
  "datadoghq.eu",
  "ap1.datadoghq.com",
  "ap2.datadoghq.com",
  "ddog-gov.com",
].map((site) => ({ value: site, label: site }));

function SetupAlert() {
  return (
    <Alert
      type="warning"
      showIcon
      title="Datadog isn't configured"
      description="Add a Datadog API key, an application key and your site below (Datadog → Organization Settings → API Keys and Application Keys). The application key needs read access to Software Catalog, Incidents and DORA Metrics. Atlas only reads from Datadog. Until then Sync Datadog is off."
    />
  );
}

/** "datadog" jobs are this card's; the status shows the running job of any kind. */
function runningNote(status: DatadogStatus | undefined, own: boolean): string | null {
  const running = status?.running;
  if (!running || own) return null;
  return running.kind === "datadog"
    ? "A Datadog sync is running."
    : "Another sync is running; wait for it to finish.";
}

function SyncDatadog({
  organizationId,
  status,
}: {
  organizationId: string | undefined;
  status: DatadogStatus | undefined;
}) {
  const sync = useDatadogSync();
  // This card's own job, running or just ended, never shows as someone else's.
  const own = sync.running || sync.datadogOutcome !== undefined || sync.error !== undefined;
  const note = runningNote(status, own);
  // One sync at a time server-side: any running job blocks a start.
  const busy = status?.running != null && !sync.running;
  return (
    <Flex vertical gap="small">
      <Flex wrap gap="small" align="center">
        <Button
          type="primary"
          icon={<SyncOutlined />}
          disabled={!status?.configured || !organizationId || busy}
          loading={sync.running}
          onClick={() => sync.start(organizationId)}
        >
          Sync Datadog
        </Button>
        {note && <Typography.Text type="secondary">{note}</Typography.Text>}
        {sync.datadogOutcome && (
          <Typography.Text type="secondary">
            {datadogSyncOutcome(sync.datadogOutcome)}
          </Typography.Text>
        )}
      </Flex>
      {sync.error && <Alert type="error" showIcon title="Sync failed" description={sync.error} />}
    </Flex>
  );
}

function DatadogCredentials({ status }: { status: DatadogStatus }) {
  return (
    <CredentialsSection
      integration="datadog"
      label="Datadog"
      fields={[
        { name: "api_key", label: "Datadog API key", secret: true, stored: status.hint },
        {
          name: "application_key",
          label: "Application key",
          secret: true,
          stored: status.application_key_hint,
        },
        { name: "site", label: "Site", options: SITES },
      ]}
      initial={{ site: status.site ?? SITES[0].value }}
      status={status}
      keepSecrets={false}
    />
  );
}

export function DatadogConnectorCard({ organizationId }: { organizationId: string | undefined }) {
  const query = useDatadogStatus();
  const status = query.data;
  const badge = status?.configured ? (
    <Badge status="success" text={`Configured · ${status.site ?? ""}`} />
  ) : (
    <Badge status="default" text="Not configured" />
  );
  return (
    <Card title="Datadog" loading={query.isLoading} extra={query.isLoading ? null : badge}>
      <Flex vertical gap="middle">
        {query.error && (
          <Alert
            type="error"
            showIcon
            title="Failed to load Datadog status"
            description={query.error.message}
          />
        )}
        {status?.configured === false && <SetupAlert />}
        <SyncDatadog organizationId={organizationId} status={status} />
        {status?.configured && organizationId && (
          <CodebasesTable organizationId={organizationId} source="datadog" />
        )}
        {status && <DatadogCredentials status={status} />}
      </Flex>
    </Card>
  );
}
