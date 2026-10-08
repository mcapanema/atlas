import { Alert, Descriptions, Flex, Skeleton, Typography } from "antd";

import { useSyncSchedule, type SyncSchedule } from "../api/syncSchedule";
import { formatInZone, lastSync } from "../lib/syncSchedule";

function nextRun(schedule: SyncSchedule | null): string {
  if (!schedule) return "Not scheduled";
  return schedule.next_run_at
    ? formatInZone(schedule.next_run_at, schedule.timezone)
    : "Auto sync is off";
}

function LastSyncText({ schedule }: { schedule: SyncSchedule | null }) {
  // The server records manual syncs only on an existing schedule row, so a
  // missing or empty row means the last sync is unknown, not absent.
  const last = schedule ? lastSync(schedule) : null;
  if (!schedule || !last) return <Typography.Text type="secondary">Not recorded</Typography.Text>;
  const when = formatInZone(last.at, schedule.timezone);
  return last.error ? (
    <Typography.Text type="danger">{`Failed · ${when}`}</Typography.Text>
  ) : (
    <Typography.Text>{`${when} · ${last.kind}`}</Typography.Text>
  );
}

/** When the organization's Linear data last landed and when it lands next. */
export function SyncStatus({ organizationId }: { organizationId: string }) {
  const query = useSyncSchedule(organizationId);
  if (query.isLoading) return <Skeleton active title={false} paragraph={{ rows: 1 }} />;
  // AutoSyncCard reports a failed load once; don't repeat it here.
  if (query.isError) return null;
  const schedule = query.data ?? null;
  const failure = schedule ? lastSync(schedule)?.error : null;
  return (
    <Flex vertical gap="small">
      <Descriptions
        size="small"
        column={{ xs: 1, sm: 2 }}
        items={[
          { key: "last", label: "Last sync", children: <LastSyncText schedule={schedule} /> },
          { key: "next", label: "Next run", children: nextRun(schedule) },
        ]}
      />
      {failure && (
        <Alert type="error" showIcon title="Last auto sync failed" description={failure} />
      )}
    </Flex>
  );
}
