import { SyncOutlined } from "@ant-design/icons";
import { Button, Space, Tooltip, Typography } from "antd";

import { useLinearStatus, useTeamSync } from "../api/connectors";
import type { Team } from "../api/teams";
import { syncOutcome } from "../lib/syncOutcome";

/** Pulls one team's latest issues from Linear; the dashboard refetches on success. */
export function TeamSyncButton({ team }: { team: Team }) {
  const sync = useTeamSync(team.id);
  // Every sync takes one lock (ADR-0014): a click waits for a running auto sync.
  const autoSyncing = useLinearStatus().data?.auto_syncing ?? false;
  const fromSource = team.external_id !== null;
  // Its own wrapping row: the wait hint and the outcome sit beside the button.
  return (
    <Space wrap>
      <Tooltip title={fromSource ? undefined : "Created in Atlas, so there is nothing to sync"}>
        <Button
          icon={<SyncOutlined />}
          disabled={!fromSource}
          loading={sync.isPending}
          onClick={() => sync.mutate()}
        >
          Sync team
        </Button>
      </Tooltip>
      {autoSyncing && (
        <Typography.Text type="secondary">
          An automatic sync is running; Sync team starts when it finishes.
        </Typography.Text>
      )}
      {sync.isError && <Typography.Text type="danger">{sync.error.message}</Typography.Text>}
      {sync.data && <Typography.Text type="secondary">{syncOutcome(sync.data)}</Typography.Text>}
    </Space>
  );
}
