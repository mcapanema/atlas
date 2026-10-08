import { SyncOutlined } from "@ant-design/icons";
import { Button, Tooltip, Typography } from "antd";

import { useTeamSync, type SyncSummary } from "../api/connectors";
import type { Team } from "../api/teams";

function outcome(summary: SyncSummary): string {
  if (summary.work_items === 0 && summary.events === 0) return "Already up to date";
  return `Updated ${summary.work_items} work items · ${summary.events} events`;
}

/** Pulls one team's latest issues from Linear; the dashboard refetches on success. */
export function TeamSyncButton({ team }: { team: Team }) {
  const sync = useTeamSync(team.id);
  const fromSource = team.external_id !== null;
  return (
    <>
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
      {sync.isError && <Typography.Text type="danger">{sync.error.message}</Typography.Text>}
      {sync.data && <Typography.Text type="secondary">{outcome(sync.data)}</Typography.Text>}
    </>
  );
}
