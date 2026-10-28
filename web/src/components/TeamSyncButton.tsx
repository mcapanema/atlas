import { SyncOutlined } from "@ant-design/icons";
import { Button, Space, Tooltip, Typography } from "antd";

import { useLinearStatus, useTeamSync } from "../api/connectors";
import type { Team } from "../api/teams";
import { syncOutcome } from "../lib/syncOutcome";

/** Pulls one team's latest issues from Linear; the dashboard refetches on success. */
export function TeamSyncButton({ team }: { team: Team }) {
  const sync = useTeamSync(team.id);
  // Every sync takes one lock (ADR-0014): someone else's running job is not tracked here.
  const otherRunning = (useLinearStatus().data?.running ?? null) !== null && !sync.running;
  const fromSource = team.external_id !== null;
  // Its own wrapping row: the wait hint and the outcome sit beside the button.
  return (
    <Space wrap>
      <Tooltip title={fromSource ? undefined : "Created in Atlas, so there is nothing to sync"}>
        <Button
          icon={<SyncOutlined />}
          disabled={!fromSource}
          loading={sync.running}
          onClick={() => sync.start()}
        >
          Sync team
        </Button>
      </Tooltip>
      {otherRunning && (
        <Typography.Text type="secondary">
          A sync is running; Sync team shows its result.
        </Typography.Text>
      )}
      {sync.error && <Typography.Text type="danger">{sync.error}</Typography.Text>}
      {sync.outcome && (
        <Typography.Text type="secondary">{syncOutcome(sync.outcome)}</Typography.Text>
      )}
    </Space>
  );
}
