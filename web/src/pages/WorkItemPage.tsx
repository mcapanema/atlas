import { Alert, Card, Descriptions, Space, Table, Tag, Timeline, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useParams } from "react-router-dom";

import { useWorkItemEvents, type WorkItemEvent } from "../api/events";
import { SourceLink } from "../components/SourceLink";
import {
  type BlockedPeriod,
  type StatePeriod,
  type WorkItem,
  useWorkItem,
  useWorkItemTimeline,
} from "../api/workItems";
import { formatDateTime } from "../lib/dates";
import { formatDuration } from "../lib/duration";

const stateColumns: ColumnsType<StatePeriod> = [
  { title: "State", dataIndex: "state" },
  {
    title: "Entered",
    dataIndex: "entered_at",
    render: (enteredAt: string) => formatDateTime(enteredAt),
  },
  {
    title: "Exited",
    dataIndex: "exited_at",
    render: (exitedAt: string | null) => (exitedAt ? formatDateTime(exitedAt) : "current"),
  },
  {
    title: "Duration",
    className: "fig",
    render: (_: unknown, period: StatePeriod) =>
      formatDuration(period.entered_at, period.exited_at),
  },
];

const blockedColumns: ColumnsType<BlockedPeriod> = [
  {
    title: "Blocked at",
    dataIndex: "started_at",
    render: (startedAt: string) => formatDateTime(startedAt),
  },
  {
    title: "Unblocked at",
    dataIndex: "ended_at",
    render: (endedAt: string | null) => (endedAt ? formatDateTime(endedAt) : "still blocked"),
  },
  {
    title: "Duration",
    className: "fig",
    render: (_: unknown, period: BlockedPeriod) =>
      formatDuration(period.started_at, period.ended_at),
  },
];

function eventLabel(event: WorkItemEvent): string {
  if (event.from_state && event.to_state) {
    return `${event.type}: ${event.from_state} → ${event.to_state}`;
  }
  if (event.to_state) {
    return `${event.type} → ${event.to_state}`;
  }
  return event.type;
}

function WorkItemHeader({ workItem }: { workItem: WorkItem | undefined }) {
  return (
    <div>
      <Typography.Title level={3}>{workItem?.title}</Typography.Title>
      {workItem && (
        <Descriptions size="small" column={4}>
          <Descriptions.Item label="Type">
            <Tag>{workItem.type}</Tag>
          </Descriptions.Item>
          <Descriptions.Item label="State">
            <Tag color="blue">{workItem.state}</Tag>
          </Descriptions.Item>
          <Descriptions.Item label="Created">
            {formatDateTime(workItem.created_at)}
          </Descriptions.Item>
          <Descriptions.Item label="External id">{workItem.external_id ?? "—"}</Descriptions.Item>
          <Descriptions.Item label="Source">
            <SourceLink url={workItem.url} />
          </Descriptions.Item>
        </Descriptions>
      )}
    </div>
  );
}

function EventTimelineCard({ events }: { events: ReturnType<typeof useWorkItemEvents> }) {
  let body;
  if (events.isError) {
    body = (
      <Alert type="error" message="Failed to load events" description={events.error.message} />
    );
  } else if (events.data?.length) {
    body = (
      <Timeline
        items={events.data.map((event) => ({
          children: `${formatDateTime(event.occurred_at)} — ${eventLabel(event)}`,
        }))}
      />
    );
  } else {
    body = <Typography.Text type="secondary">No events recorded yet.</Typography.Text>;
  }
  return (
    <Card title="Event timeline" loading={events.isLoading}>
      {body}
    </Card>
  );
}

function TimelineError({ error }: { error: Error }) {
  return <Alert type="error" message="Failed to load timeline" description={error.message} />;
}

function StatePeriodsCard({ timeline }: { timeline: ReturnType<typeof useWorkItemTimeline> }) {
  return (
    <Card title="Time in state" loading={timeline.isLoading}>
      {timeline.isError ? (
        <TimelineError error={timeline.error} />
      ) : (
        <Table
          rowKey={(period: StatePeriod) => `${period.state}-${period.entered_at}`}
          pagination={false}
          dataSource={timeline.data?.state_periods ?? []}
          columns={stateColumns}
        />
      )}
    </Card>
  );
}

function BlockedPeriodsCard({ timeline }: { timeline: ReturnType<typeof useWorkItemTimeline> }) {
  let body;
  if (timeline.isError) {
    body = <TimelineError error={timeline.error} />;
  } else if (timeline.data?.blocked_periods.length) {
    body = (
      <Table
        rowKey={(period: BlockedPeriod) => period.started_at}
        pagination={false}
        dataSource={timeline.data.blocked_periods}
        columns={blockedColumns}
      />
    );
  } else {
    body = <Typography.Text type="secondary">Never blocked.</Typography.Text>;
  }
  return (
    <Card title="Blocked periods" loading={timeline.isLoading}>
      {body}
    </Card>
  );
}

export function WorkItemPage() {
  const { id = "" } = useParams();
  const workItem = useWorkItem(id);
  const events = useWorkItemEvents(id);
  const timeline = useWorkItemTimeline(id);

  if (workItem.isError) {
    return <Alert type="error" message="Work item not found" />;
  }

  return (
    <Space direction="vertical" style={{ width: "100%" }} size="large">
      <WorkItemHeader workItem={workItem.data} />
      <EventTimelineCard events={events} />
      <StatePeriodsCard timeline={timeline} />
      <BlockedPeriodsCard timeline={timeline} />
    </Space>
  );
}
