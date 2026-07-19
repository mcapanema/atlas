import { Alert, Card, Descriptions, Space, Table, Tag, Timeline, Typography } from "antd";
import { useParams } from "react-router-dom";

import { useWorkItemEvents, type WorkItemEvent } from "../api/events";
import {
  type BlockedPeriod,
  type StatePeriod,
  useWorkItem,
  useWorkItemTimeline,
} from "../api/workItems";
import { formatDateTime } from "../lib/dates";
import { formatDuration } from "../lib/duration";

function eventLabel(event: WorkItemEvent): string {
  if (event.from_state && event.to_state) {
    return `${event.type}: ${event.from_state} → ${event.to_state}`;
  }
  if (event.to_state) {
    return `${event.type} → ${event.to_state}`;
  }
  return event.type;
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
      <div>
        <Typography.Title level={3}>{workItem.data?.title}</Typography.Title>
        {workItem.data && (
          <Descriptions size="small" column={4}>
            <Descriptions.Item label="Type">
              <Tag>{workItem.data.type}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label="State">
              <Tag color="blue">{workItem.data.state}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label="Created">
              {formatDateTime(workItem.data.created_at)}
            </Descriptions.Item>
            <Descriptions.Item label="External id">
              {workItem.data.external_id ?? "—"}
            </Descriptions.Item>
          </Descriptions>
        )}
      </div>
      <Card title="Event timeline" loading={events.isLoading}>
        {events.isError ? (
          <Alert type="error" message="Failed to load events" description={events.error.message} />
        ) : events.data?.length ? (
          <Timeline
            items={events.data.map((event) => ({
              children: `${formatDateTime(event.occurred_at)} — ${eventLabel(event)}`,
            }))}
          />
        ) : (
          <Typography.Text type="secondary">No events recorded yet.</Typography.Text>
        )}
      </Card>
      <Card title="Time in state" loading={timeline.isLoading}>
        {timeline.isError ? (
          <Alert
            type="error"
            message="Failed to load timeline"
            description={timeline.error.message}
          />
        ) : (
          <Table
            rowKey={(period: StatePeriod) => `${period.state}-${period.entered_at}`}
            pagination={false}
            dataSource={timeline.data?.state_periods ?? []}
            columns={[
              { title: "State", dataIndex: "state" },
              {
                title: "Entered",
                dataIndex: "entered_at",
                render: (enteredAt: string) => formatDateTime(enteredAt),
              },
              {
                title: "Exited",
                dataIndex: "exited_at",
                render: (exitedAt: string | null) =>
                  exitedAt ? formatDateTime(exitedAt) : "current",
              },
              {
                title: "Duration",
                className: "fig",
                render: (_: unknown, period: StatePeriod) =>
                  formatDuration(period.entered_at, period.exited_at),
              },
            ]}
          />
        )}
      </Card>
      <Card title="Blocked periods" loading={timeline.isLoading}>
        {timeline.isError ? (
          <Alert
            type="error"
            message="Failed to load timeline"
            description={timeline.error.message}
          />
        ) : timeline.data?.blocked_periods.length ? (
          <Table
            rowKey={(period: BlockedPeriod) => period.started_at}
            pagination={false}
            dataSource={timeline.data.blocked_periods}
            columns={[
              {
                title: "Blocked at",
                dataIndex: "started_at",
                render: (startedAt: string) => formatDateTime(startedAt),
              },
              {
                title: "Unblocked at",
                dataIndex: "ended_at",
                render: (endedAt: string | null) =>
                  endedAt ? formatDateTime(endedAt) : "still blocked",
              },
              {
                title: "Duration",
                className: "fig",
                render: (_: unknown, period: BlockedPeriod) =>
                  formatDuration(period.started_at, period.ended_at),
              },
            ]}
          />
        ) : (
          <Typography.Text type="secondary">Never blocked.</Typography.Text>
        )}
      </Card>
    </Space>
  );
}
