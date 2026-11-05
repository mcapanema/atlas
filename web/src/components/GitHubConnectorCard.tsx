import { SyncOutlined } from "@ant-design/icons";
import { Alert, Badge, Button, Card, Flex, Typography } from "antd";

import { useGitHubStatus, useGitHubSync, type GitHubStatus } from "../api/connectors";
import { codeSyncOutcome } from "../lib/syncOutcome";
import { CodebasesTable } from "./CodebasesTable";
import { CredentialsSection } from "./CredentialsSection";

function SetupAlert() {
  return (
    <Alert
      type="warning"
      showIcon
      title="GitHub isn't configured"
      description="Add a GitHub token and owner below: a fine-grained personal access token (GitHub → Settings → Developer settings) with read access to Metadata, Contents, Pull requests and Deployments on the repositories Atlas should see. Until then Sync GitHub is off."
    />
  );
}

/** "code" jobs are GitHub's; the status shows the running job of any kind. */
function runningNote(status: GitHubStatus | undefined, own: boolean): string | null {
  const running = status?.running;
  if (!running || own) return null;
  return running.kind === "code"
    ? "A GitHub sync is running."
    : "Another sync is running; wait for it to finish.";
}

function SyncGitHub({
  organizationId,
  status,
}: {
  organizationId: string | undefined;
  status: GitHubStatus | undefined;
}) {
  const sync = useGitHubSync();
  // This card's own job, running or just ended, never shows as someone else's.
  const own = sync.running || sync.codeOutcome !== undefined || sync.error !== undefined;
  const note = runningNote(status, own);
  // One sync at a time server-side: any running job, GitHub's or Linear's, blocks a start.
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
          Sync GitHub
        </Button>
        {note && <Typography.Text type="secondary">{note}</Typography.Text>}
        {sync.codeOutcome && (
          <Typography.Text type="secondary">{codeSyncOutcome(sync.codeOutcome)}</Typography.Text>
        )}
      </Flex>
      {sync.error && <Alert type="error" showIcon title="Sync failed" description={sync.error} />}
    </Flex>
  );
}

function GitHubCredentials({ status }: { status: GitHubStatus }) {
  return (
    <CredentialsSection
      integration="github"
      label="GitHub"
      fields={[
        { name: "token", label: "GitHub token", secret: true, stored: status.hint },
        { name: "owner", label: "Owner (organization or user)" },
      ]}
      initial={{ owner: status.owner ?? "" }}
      status={status}
    />
  );
}

export function GitHubConnectorCard({ organizationId }: { organizationId: string | undefined }) {
  const query = useGitHubStatus();
  const status = query.data;
  const badge = status?.configured ? (
    <Badge status="success" text={`Configured · ${status.owner ?? ""}`} />
  ) : (
    <Badge status="default" text="Not configured" />
  );
  return (
    <Card title="GitHub" loading={query.isLoading} extra={query.isLoading ? null : badge}>
      <Flex vertical gap="middle">
        {query.error && (
          <Alert
            type="error"
            showIcon
            title="Failed to load GitHub status"
            description={query.error.message}
          />
        )}
        {status?.configured === false && <SetupAlert />}
        <SyncGitHub organizationId={organizationId} status={status} />
        {status?.configured && organizationId && (
          <CodebasesTable organizationId={organizationId} source="github" />
        )}
        {status && <GitHubCredentials status={status} />}
      </Flex>
    </Card>
  );
}
